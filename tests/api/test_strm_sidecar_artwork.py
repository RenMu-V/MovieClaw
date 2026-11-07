"""STRM sidecar artwork finding bug fix (TDD RED phase).

Reproduces the bug where .strm files can't find their sidecars because
p115 plugin generates sidecar files with the video stem WITHOUT .strm suffix,
but find_artwork receives the full .strm path and uses its stem which includes .mp4.

Example:
  video = '104DANDY-931.mp4.strm'
  video.stem = '104DANDY-931.mp4'  (stem strips .strm)
  searches for '104DANDY-931.mp4-poster.jpg'
  but p115 creates '104DANDY-931-poster.jpg'  (without .mp4)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from movieclaw_api.services.library.artwork import find_artwork
from movieclaw_db.models import FileSource, LibraryFile


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def _row(path: Path) -> LibraryFile:
    return LibraryFile(
        library_id=1, file_path=str(path), size_bytes=1, container="mp4", source=FileSource.SCANNED
    )


def test_strm_file_finds_sidecar_without_strm_suffix(tmp_path: Path) -> None:
    """STRM file should find sidecars named after the base video name.
    
    p115 plugin creates: video_name-poster.jpg (no .strm, no .mp4)
    find_artwork receives: video_name.mp4.strm
    
    Without fix: searches for "video_name.mp4-poster.jpg" → NOT FOUND
    With fix: searches for "video_name-poster.jpg" → FOUND
    """
    # Create a .strm file pointing to a virtual p115 video
    strm_file = _touch(tmp_path / "104DANDY-931.mp4.strm")
    
    # p115 plugin creates sidecar with this naming: base video stem + suffix
    # The base video is conceptually "104DANDY-931.mp4" but sidecar drops the .mp4
    poster_sidecar = _touch(tmp_path / "104DANDY-931-poster.jpg")
    
    # This should find the poster, but currently fails
    result = find_artwork(strm_file.parent, "poster", [strm_file])
    assert result == poster_sidecar, (
        f"Expected to find {poster_sidecar.name}, but got {result.name if result else 'None'}. "
        f"STRM files need special handling: strip .strm before searching for sidecars."
    )


def test_strm_file_finds_fanart_sidecar(tmp_path: Path) -> None:
    """STRM backdrop/fanart search should also handle .strm suffix correctly."""
    strm_file = _touch(tmp_path / "104DANDY-931.mp4.strm")
    fanart_sidecar = _touch(tmp_path / "104DANDY-931-fanart.jpg")
    
    result = find_artwork(strm_file.parent, "fanart", [strm_file])
    assert result == fanart_sidecar


def test_strm_file_ignores_mp4_suffixed_sidecars(tmp_path: Path) -> None:
    """Verify that sidecars with .mp4 in the name are NOT used for .strm files.
    
    Only the video base name (without .strm AND without .mp4) should match.
    """
    strm_file = _touch(tmp_path / "104DANDY-931.mp4.strm")
    
    # These should NOT be found by the strm file
    _touch(tmp_path / "104DANDY-931.mp4-poster.jpg")  # Wrong: has .mp4
    
    # But this one should be found
    correct_poster = _touch(tmp_path / "104DANDY-931-poster.jpg")
    
    result = find_artwork(strm_file.parent, "poster", [strm_file])
    assert result == correct_poster
