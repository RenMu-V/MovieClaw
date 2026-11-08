from tests.api.test_library_video_kind import db
from movieclaw_db.models import Library, LibraryFile, MediaItem
from movieclaw_api.services.media_scrape import _media_dir_lookup

async def test_mixed_media_directory_lookup_does_not_drop_concrete_movie(db,tmp_path):
    async with db.session() as s:
        lib=Library(name='Mixed',kind='mixed',source='tmdb',root_paths=[str(tmp_path)])
        item=MediaItem(kind='movie',source='tmdb',tmdb_id=987,title='Movie',original_title='Movie')
        s.add(lib);s.add(item);await s.flush()
        file=tmp_path/'Movie (2020)'/'Movie.strm';file.parent.mkdir();file.write_text('https://invalid.example/')
        s.add(LibraryFile(library_id=lib.id,media_item_id=item.id,file_path=str(file),size_bytes=1,source='scanned'))
        await s.commit()
        lookup=await _media_dir_lookup(s,item,[])
        assert lookup is not None
        assert file in lookup._videos
