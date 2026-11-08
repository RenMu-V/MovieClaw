from pathlib import Path
import pytest
from sqlmodel import select
from PIL import Image
from tests.api.test_library_video_kind import db
from movieclaw_api.services.library import scan as scan_mod
from movieclaw_api.services.library.config import LibraryConfigService
from movieclaw_api.services.library.profile import profile_for
from movieclaw_api.services.library.thumbs import ensure_local_assets
from movieclaw_db.models import LibraryFile,MediaItem,MediaMetadata
from movieclaw_media.models import MediaKind

def test_local_movie_profile_preserves_movie_projection():
    p=profile_for('movie','local')
    assert p.kind is MediaKind.MOVIE and not p.scraped
    assert (p.jellyfin_type,p.jellyfin_collection)==('Movie','movies')

async def test_local_movie_scan_without_tmdb_even_with_generic_nfo_id(db,tmp_path,monkeypatch):
    root=tmp_path/'movies'; root.mkdir()
    f=root/'ABC-123.strm';f.write_text('https://invalid.example/video')
    f.with_suffix('.nfo').write_text('<movie><title>Local Movie</title><plot>Local plot</plot><id>ABC-123</id><actor><name>Actor A</name></actor></movie>')
    (root/'NoNfo.strm').write_text('https://invalid.example/other')
    Image.new('RGB',(120,180),'red').save(root/'ABC-123-poster.jpg')
    Image.new('RGB',(320,180),'blue').save(root/'ABC-123-fanart.jpg')
    async with db.session() as s:
        lib=await LibraryConfigService(s).create(name='Local Movies',kind=MediaKind.MOVIE,source='local',root_paths=[str(root)],generate_thumbnails=False,detect_media_segments=False)
    def unavailable():raise AssertionError('local movie must not initialize TMDB')
    monkeypatch.setattr(scan_mod,'get_tmdb_client',unavailable)
    result=await scan_mod.scan_library(lib.id)
    assert not result.errors and result.identified==2 and result.unidentified==0
    async with db.session() as s:
        items=(await s.execute(select(MediaItem))).scalars().all()
        assert len(items)==2 and all(i.kind=='movie' and i.source=='local' and i.tmdb_id is None for i in items)
        item=next(i for i in items if i.title=='Local Movie'); stable={i.external_id for i in items}
        meta=(await s.execute(select(MediaMetadata).where(MediaMetadata.media_item_id==item.id))).scalar_one()
        assert meta.overview=='Local plot' and meta.cast[0]['name']=='Actor A'
    await ensure_local_assets(item.id)
    async with db.session() as s:
        meta=(await s.execute(select(MediaMetadata).where(MediaMetadata.media_item_id==item.id))).scalar_one()
        assert (meta.poster_width,meta.poster_height)==(120,180)
        assert meta.poster_file and meta.backdrop_file
    await scan_mod.scan_library(lib.id)
    async with db.session() as s:
        assert {i.external_id for i in (await s.execute(select(MediaItem))).scalars()}==stable
