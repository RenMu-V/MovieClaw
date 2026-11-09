"""Normal scan -> native asset stage, not manual ensure/refresh."""
from io import BytesIO
import httpx
import pytest
from PIL import Image
from sqlmodel import select
from tests.api.test_library_video_kind import db
from movieclaw_api.services import media_scrape, media_discover, image_proxy
from movieclaw_api.services.library import scan
from movieclaw_api.services.library.config import LibraryConfigService
from movieclaw_db.models import MediaItem, MediaMetadata, LibraryFile
from movieclaw_media.models import LibraryKind
from movieclaw_media.tmdb import TmdbClient

_REAL_ENSURE = media_scrape.ensure_assets

@pytest.mark.parametrize('kind', ['movie', 'tv'])
async def test_normal_scan_automatically_fills_nfo_art(db, tmp_path, monkeypatch, kind):
    monkeypatch.setattr(media_scrape, 'assets_root', lambda: tmp_path / 'assets')
    monkeypatch.setattr(media_scrape, 'ensure_assets', _REAL_ENSURE)
    root = tmp_path / 'media'; root.mkdir()
    show = root / 'Local title (2020)'; show.mkdir()
    if kind == 'tv':
        (show / 'tvshow.nfo').write_text('<tvshow><title>Local title</title><year>2020</year><uniqueid type="tmdb">42</uniqueid></tvshow>')
        season = show / 'Season 1'; season.mkdir()
        video = season / 'Local title S01E01.strm'
    else:
        video = show / 'Local title.strm'
        video.with_suffix('.nfo').write_text('<movie><title>Local title</title><year>2020</year><uniqueid type="tmdb">42</uniqueid></movie>')
    video.write_text('https://example.invalid/never-read')
    calls = []
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={'id':42, 'title':'Local title', 'name':'Local title', 'release_date':'2020-01-01', 'first_air_date':'2020-01-01', 'poster_path':'/poster.jpg','backdrop_path':'/back.jpg'})
    client = TmdbClient('test',transport=httpx.MockTransport(handler))
    monkeypatch.setattr(media_discover, 'get_tmdb_client', lambda: client)
    monkeypatch.setattr(scan, 'get_tmdb_client', lambda: client)
    class Proxy:
        async def fetch(self, *args, **kwargs):
            out = BytesIO(); Image.new('RGB',(120,180),'blue').save(out,'JPEG')
            return out.getvalue(), 'image/jpeg'
    monkeypatch.setattr(image_proxy, 'get_image_proxy', lambda: Proxy())
    async with db.session() as s:
        lib = await LibraryConfigService(s).create(name='Automatic art', kind=LibraryKind.MIXED if kind == 'tv' else LibraryKind.MOVIE, source='tmdb', root_paths=[str(root)],generate_thumbnails=False,detect_media_segments=False)
    result = await scan.scan_library(lib.id)
    assert not result.errors and result.identified == 1 and result.unidentified == 0
    async with db.session() as s:
        item = (await s.execute(select(MediaItem))).scalar_one()
        meta = (await s.execute(select(MediaMetadata))).scalar_one()
        file = (await s.execute(select(LibraryFile))).scalar_one()
        assert item.source == 'local' and item.tmdb_id is None
        assert not file.unidentified_code
        assert meta.poster_file and meta.backdrop_file
        with Image.open(media_scrape.assets_root() / meta.poster_file) as img:
            assert img.size == (120,180)
    await scan.scan_library(lib.id)
    assert calls == [f'/3/{kind}/42']
    await client.aclose()
