"""Exercise the real asset service with an isolated SQL database and real JPEGs."""
from pathlib import Path

import pytest
from PIL import Image
from sqlmodel import SQLModel, select

from movieclaw_api.services.library import thumbs
from movieclaw_db.engine import Database
from movieclaw_db.models import Library, LibraryFile, MediaItem, MediaMetadata, MediaSource


@pytest.mark.asyncio
async def test_disabled_video_generation_still_absorbs_sidecars(tmp_path, monkeypatch):
    from movieclaw_api.services import media_scrape

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with db.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    monkeypatch.setattr(thumbs, "get_database", lambda: db)
    monkeypatch.setattr(media_scrape, "assets_root", lambda: tmp_path / "assets")
    video = tmp_path / "ABC-123.strm"
    video.write_text("https://example.invalid/never-read")
    Image.new("RGB", (200, 300), "red").save(tmp_path / "ABC-123-poster.jpg")
    Image.new("RGB", (640, 360), "blue").save(tmp_path / "ABC-123-fanart.jpg")
    original_run = thumbs.subprocess.run

    def guarded_run(cmd, *args, **kwargs):
        assert str(video) not in cmd, "disabled switch must never read/probe video"
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(thumbs.subprocess, "run", guarded_run)
    async with db.session() as session:
        library = Library(name="local", kind="video", source="local", generate_thumbnails=False)
        item = MediaItem(kind="video", source=MediaSource.LOCAL, title="ABC-123",
                         original_title="ABC-123", external_id="local:test")
        session.add_all([library, item])
        await session.commit()
        session.add(LibraryFile(library_id=library.id, media_item_id=item.id,
                                file_path=str(video), size_bytes=1, source="scan"))
        await session.commit()
        item_id = item.id
    try:
        await thumbs.ensure_local_assets(item_id)
        async with db.session() as session:
            meta = (await session.execute(select(MediaMetadata))).scalar_one_or_none()
            assert meta is not None and meta.poster_file == f"{item_id}/poster.jpg"
            assert (meta.poster_width, meta.poster_height) == (200, 300)
            assert meta.backdrop_file == f"{item_id}/backdrop.jpg"
        for name in ("poster.jpg", "backdrop.jpg"):
            with Image.open(tmp_path / "assets" / str(item_id) / name) as image:
                image.verify()
        # Force refresh after sidecars disappear must not fall through to video I/O.
        (tmp_path / "ABC-123-poster.jpg").unlink()
        (tmp_path / "ABC-123-fanart.jpg").unlink()
        await thumbs.ensure_local_assets(item_id, force=True)
        async with db.session() as session:
            meta = (await session.execute(select(MediaMetadata))).scalar_one()
            assert meta.backdrop_file is None
    finally:
        await db.dispose()


def test_disabled_without_sidecars_does_not_launch_subprocess(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("no sidecars + disabled generation must never launch ffmpeg/ffprobe")

    monkeypatch.setattr(thumbs.subprocess, "run", forbidden)
    assert thumbs.build_thumbnail(tmp_path / "missing.mkv", tmp_path / "poster.jpg",
                                  duration_seconds=None, allow_video=False) is None


@pytest.mark.parametrize("embedded", [True, False])
def test_enabled_keeps_embedded_cover_then_frame_fallback(tmp_path, monkeypatch, embedded):
    video, dest = tmp_path / "clip.mkv", tmp_path / "poster.jpg"
    calls = []

    def probe(path):
        calls.append("probe")
        assert path == video
        return 2 if embedded else None

    def extract(path, index, target):
        calls.append("embedded")
        assert path == video and index == 2
        Image.new("RGB", (20, 30)).save(target)
        return True

    def grab(path, target, duration, hdr):
        calls.append("frame")
        assert path == video
        Image.new("RGB", (40, 20)).save(target)
        return True

    monkeypatch.setattr(thumbs, "_attached_pic_index", probe)
    monkeypatch.setattr(thumbs, "_extract_stream", extract)
    monkeypatch.setattr(thumbs, "_grab_frame", grab)
    assert thumbs.build_thumbnail(video, dest, duration_seconds=100) == (
        (20, 30) if embedded else (40, 20))
    assert calls == (["probe", "embedded"] if embedded else ["probe", "frame"])
