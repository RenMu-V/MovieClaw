"""Real SQLite/JPEG regression for NFO-priority image-only fallback."""
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlmodel import SQLModel, select

from movieclaw_api.services import media_scrape, media_discover, image_proxy
from movieclaw_api.services.library import thumbs
from movieclaw_db.engine import Database
from movieclaw_db.models import Library, LibraryFile, MediaItem, MediaMetadata, MediaSource
from movieclaw_media.tmdb import TmdbClient


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["ok", "offline", "no_id", "plain_id", "wrong_title", "wrong_year", "404", "null", "local_images", "locked", "backdrop_only", "concurrent"])
@pytest.mark.parametrize("kind,library_kind", [("movie", "movie"), ("tv", "mixed")])
async def test_local_identity_automatically_gets_only_missing_images(tmp_path, monkeypatch, kind, library_kind, scenario):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    for mod in (thumbs, media_scrape):
        monkeypatch.setattr(mod, "get_database", lambda: db)
    monkeypatch.setattr(media_scrape, "assets_root", lambda: tmp_path / "assets")
    video = tmp_path / ("__series__.strm" if kind == 'tv' else "sample.strm")
    video.write_text("https://example.invalid/do-not-read")
    nfo = tmp_path / ("tvshow.nfo" if kind == "tv" else "sample.nfo")
    tag = "tvshow" if kind == "tv" else "movie"
    nfo.write_text(f'<{tag}><title>Local title</title><year>2020</year><plot>Local plot</plot><uniqueid type="tmdb">42</uniqueid></{tag}>')
    if scenario in ('no_id', 'plain_id'):
        nfo.write_text(f'<{tag}><title>Local title</title><id>42</id></{tag}>')
    if scenario == 'local_images':
        Image.new('RGB', (80, 120), 'red').save(tmp_path / 'poster.jpg')
        Image.new('RGB', (160, 90), 'red').save(tmp_path / 'fanart.jpg')
    calls = []
    def api(request):
        calls.append(request.url.path)
        if scenario == '404':
            return httpx.Response(404)
        name = 'Wrong film' if scenario == 'wrong_title' else 'Local title'
        date = '1999-01-01' if scenario == 'wrong_year' else '2020-01-01'
        return httpx.Response(200, json={"id": 42, "title": name, "name": name, "release_date": date, "first_air_date": date, "poster_path": None if scenario == 'null' else "/poster.jpg", "backdrop_path": None if scenario == 'null' else "/back.jpg"})
    client = TmdbClient("test", transport=httpx.MockTransport(api))
    monkeypatch.setattr(media_discover, "get_tmdb_client", lambda: client)
    downloads = []
    class Proxy:
        async def fetch(self, url, **kwargs):
            downloads.append(url)
            b = BytesIO(); Image.new("RGB", (120, 180), "blue").save(b, "JPEG")
            return b.getvalue(), "image/jpeg"
    monkeypatch.setattr(image_proxy, "get_image_proxy", lambda: Proxy())
    async with db.session() as s:
        lib = Library(name="test", kind=library_kind, source="local" if scenario == 'offline' else "tmdb", root_paths=[str(tmp_path)], generate_thumbnails=False)
        item = MediaItem(kind=kind, source=MediaSource.LOCAL, title="Local title", original_title="Local title", year=2020, external_id="local:test")
        s.add_all([lib, item]); await s.commit()
        s.add(LibraryFile(library_id=lib.id, media_item_id=item.id, file_path=str(video), size_bytes=1, source="scan"))
        meta = MediaMetadata(media_item_id=item.id, overview="Local plot")
        if scenario in ('locked', 'backdrop_only'):
            dest = tmp_path / 'assets' / str(item.id) / 'poster.jpg'
            dest.parent.mkdir(parents=True)
            Image.new('RGB', (80, 120), 'green').save(dest)
            meta.poster_file = f'{item.id}/poster.jpg'
            if scenario == 'locked':
                meta.poster_locked = meta.backdrop_locked = True
        s.add(meta); await s.commit()
        item_id = item.id
    try:
        if scenario == 'concurrent':
            import asyncio
            await asyncio.gather(*(media_scrape.ensure_assets(item_id) for _ in range(3)))
        else:
            await media_scrape.ensure_assets(item_id)
        async with db.session() as s:
            meta = (await s.execute(select(MediaMetadata))).scalar_one()
            item = await s.get(MediaItem, item_id)
            assert item.source == MediaSource.LOCAL and item.tmdb_id is None
            assert item.title == "Local title" and meta.overview == "Local plot"
            success = scenario in ('ok', 'concurrent', 'local_images', 'backdrop_only')
            if success:
                assert meta.poster_file and meta.backdrop_file
            elif scenario == 'locked':
                assert meta.poster_file and not meta.backdrop_file
            else:
                assert not meta.poster_file and not meta.backdrop_file
            poster = tmp_path / "assets" / (meta.poster_file or 'absent')
            original = poster.read_bytes() if poster.is_file() else None
        await media_scrape.ensure_assets(item_id)
        if scenario == 'locked':
            Image.new('RGB', (90, 130), 'red').save(tmp_path / 'poster.jpg')
            await thumbs.ensure_local_assets(item_id, force=True)
        if original:
            assert poster.read_bytes() == original
        assert calls == ([] if scenario in ('offline', 'no_id', 'plain_id', 'local_images', 'locked') else [f"/3/{kind}/42"])
        assert len(downloads) == (2 if scenario in ('ok', 'concurrent') else 1 if scenario == 'backdrop_only' else 0)
    finally:
        await client.aclose(); await db.dispose()


@pytest.mark.parametrize('kind', ['movie', 'tv'])
@pytest.mark.parametrize('xml,tag,expected', [
    ('<uniqueid type="tmdb">42</uniqueid>', '', 42),
    ('<id>42</id>', '', None),
    ('<uniqueid type="tmdb">42</uniqueid>', '{tmdb-43}', None),
    ('<uniqueid type="tmdb">42</uniqueid>', '{tmdb-42}', 42),
])
def test_trusted_id_is_typed_and_conflicts_fail_closed(tmp_path, kind, xml, tag, expected):
    from movieclaw_api.services.library.local_artwork import trusted_id
    root = tmp_path / tag if tag else tmp_path
    root.mkdir(exist_ok=True)
    video = root / 'sample.strm'
    nfo = root / ('tvshow.nfo' if kind == 'tv' else 'sample.nfo')
    element = 'tvshow' if kind == 'tv' else 'movie'
    nfo.write_text(f'<{element}>{xml}</{element}>')
    assert trusted_id(video, kind) == expected
    assert trusted_id(video, 'movie' if kind == 'tv' else 'tv') is None
