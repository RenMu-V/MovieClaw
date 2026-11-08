from pathlib import Path
import pytest
from sqlmodel import select
from PIL import Image
from tests.api.test_library_video_kind import db
from movieclaw_api.services.library import scan as scan_mod
from movieclaw_api.services.library.config import LibraryConfigService
from movieclaw_media.models import LibraryKind
from movieclaw_db.models import LibraryFile, MediaItem

@pytest.mark.parametrize('source',['tmdb','local'])
async def test_mixed_real_layout_offline_series_and_movie(db,tmp_path,monkeypatch,source):
    root=tmp_path/'mixed'; root.mkdir()
    for title,nfo in [('不速之親 XXX (2019)',True),('兴风作浪的姐姐(2025)',False)]:
        d=root/title; season=d/'Season 1';season.mkdir(parents=True)
        if nfo:(d/'tvshow.nfo').write_text('<tvshow><title>不速之親 XXX</title><year>2019</year></tvshow>')
        Image.new('RGB',(120,180),'red').save(d/'Cover.jpg')
        for ep in [1,2]:
            f=season/f'{title}S01E{ep:02d}.strm';f.write_text('https://invalid.example/video')
            if nfo:
                f.with_suffix('.nfo').write_text(f'<episodedetails><title>Episode {ep}</title><season>1</season><episode>{ep}</episode></episodedetails>')
            Image.new('RGB',(240,135),'blue').save(f.with_name(f.stem+'-thumb.jpg'))
    d=root/'Movie (2020)';d.mkdir();(d/'Movie.strm').write_text('https://invalid.example/movie');(d/'Movie.nfo').write_text('<movie><title>Sibling Movie</title></movie>')
    async with db.session() as s:
        lib=await LibraryConfigService(s).create(name='Mixed offline',kind=LibraryKind.MIXED,source=source,root_paths=[str(root)],generate_thumbnails=False,detect_media_segments=False)
    import httpx
    from movieclaw_media.tmdb import TmdbClient
    def fail(request):raise AssertionError('local evidence must not access online provider')
    monkeypatch.setattr(scan_mod,'get_tmdb_client',lambda:TmdbClient('key',transport=httpx.MockTransport(fail)))
    result=await scan_mod.scan_library(lib.id)
    assert not result.errors and result.identified==5 and result.unidentified==0
    async with db.session() as s:
        rows=(await s.execute(select(LibraryFile))).scalars().all();items=(await s.execute(select(MediaItem))).scalars().all()
        assert len(items)==3
        assert sorted(i.kind for i in items)==['movie','tv','tv']
        assert all(r.unidentified_code is None for r in rows)
        assert {(r.season_number,r.episode_number) for r in rows if r.season_number}=={(1,1),(1,2)}
    from movieclaw_api.services.library.thumbs import ensure_local_assets
    from movieclaw_db.models import MediaMetadata
    for item in items:
        if item.kind == 'tv':
            await ensure_local_assets(item.id)
            async with db.session() as s:
                meta=(await s.execute(select(MediaMetadata).where(MediaMetadata.media_item_id==item.id))).scalar_one()
                assert meta.poster_file and (meta.poster_width,meta.poster_height)==(120,180)
    from movieclaw_db.models import MediaSeason, MediaEpisode
    async with db.session() as s:
        assert len((await s.execute(select(MediaSeason))).scalars().all()) == 2
        assert len((await s.execute(select(MediaEpisode))).scalars().all()) == 4
    again=await scan_mod.scan_library(lib.id)
    assert not again.errors and again.unidentified==0

