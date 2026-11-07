"""POST /emby/Items/{id}/Images/Primary 为 ITEM 类型的封面替换（issue #abc）。

ITEM 类型的主封面（poster）支持 POST：接收图片二进制（raw bytes 或 multipart），
验证 mime 类型为 image/*，保存到 /app/data/metadata/images/{media_item_id}/poster.jpg，
更新 media_metadata.poster_file 字段，返回 204。

Episode/Season/Library 类型暂不支持 → 405 或 501（导读）。
"""

from __future__ import annotations

import io
import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from jellyfin.helpers import jf_login
from movieclaw_jellyfin.ids import item_guid, library_guid


def _sql(statement: str, params: tuple) -> None:
    """Execute SQL statement against test database."""
    conn = sqlite3.connect(os.environ["DATABASE_URL"].split("///", 1)[1])
    conn.execute(statement, params)
    conn.commit()
    conn.close()


def _write_image(path: Path, width: int = 200, height: int = 300) -> bytes:
    """Write a test JPEG image and return its bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (150, 100, 50))
    path.write_bytes(b"")  # ensure parent exists
    image.save(path, "JPEG")
    return path.read_bytes()


def test_post_primary_image_for_item_returns_204(
    client: TestClient, seeded: dict, tmp_path: Path
) -> None:
    """POST /Items/{item_id}/Images/Primary with JPEG returns 204."""
    token = jf_login(client)
    auth = {"ApiKey": token}
    movie = seeded["movie"]
    movie_guid = item_guid(movie)

    # Create test JPEG image
    test_image = _write_image(tmp_path / "test.jpg", 200, 300)

    # POST the image
    resp = client.post(
        f"/Items/{movie_guid}/Images/Primary",
        content=test_image,
        headers={
            **auth,
            "Content-Type": "image/jpeg",
        },
    )

    assert resp.status_code == 204, f"Expected 204, got {resp.status_code}: {resp.text}"


def test_post_primary_image_saves_to_poster_file(
    client: TestClient, seeded: dict, tmp_path: Path
) -> None:
    """Posted image is saved to /app/data/metadata/images/{id}/poster.jpg."""
    token = jf_login(client)
    auth = {"ApiKey": token}
    movie = seeded["movie"]
    movie_guid = item_guid(movie)

    # Create test image with distinct color
    test_image = _write_image(tmp_path / "test.jpg", 100, 150)

    # POST the image
    resp = client.post(
        f"/Items/{movie_guid}/Images/Primary",
        content=test_image,
        headers={**auth, "Content-Type": "image/jpeg"},
    )
    assert resp.status_code == 204

    # Verify file was saved
    poster_path = tmp_path / "metadata" / "images" / str(movie) / "poster.jpg"
    assert poster_path.is_file(), f"Poster file not found at {poster_path}"

    # Verify image content matches
    saved_image = Image.open(poster_path)
    original_image = Image.open(io.BytesIO(test_image))
    assert saved_image.size == original_image.size


def test_post_primary_image_updates_media_metadata(
    client: TestClient, seeded: dict, tmp_path: Path
) -> None:
    """Posted image updates media_metadata.poster_file in database."""
    token = jf_login(client)
    auth = {"ApiKey": token}
    movie = seeded["movie"]
    movie_guid = item_guid(movie)

    # Create test image
    test_image = _write_image(tmp_path / "test.jpg")

    # Verify initial state
    initial_query = "select poster_file from media_metadata where media_item_id = ?"
    conn = sqlite3.connect(os.environ["DATABASE_URL"].split("///", 1)[1])
    cursor = conn.execute(initial_query, (movie,))
    initial_poster = cursor.fetchone()[0]
    conn.close()

    # POST the image
    resp = client.post(
        f"/Items/{movie_guid}/Images/Primary",
        content=test_image,
        headers={**auth, "Content-Type": "image/jpeg"},
    )
    assert resp.status_code == 204

    # Verify poster_file was updated
    conn = sqlite3.connect(os.environ["DATABASE_URL"].split("///", 1)[1])
    cursor = conn.execute(initial_query, (movie,))
    updated_poster = cursor.fetchone()[0]
    conn.close()

    assert updated_poster is not None
    assert updated_poster.endswith("poster.jpg")
    assert updated_poster != initial_poster


def test_post_primary_image_rejects_non_image_mime(
    client: TestClient, seeded: dict, tmp_path: Path
) -> None:
    """POST with non-image MIME type returns 400."""
    token = jf_login(client)
    auth = {"ApiKey": token}
    movie = seeded["movie"]
    movie_guid = item_guid(movie)

    resp = client.post(
        f"/Items/{movie_guid}/Images/Primary",
        content=b"not an image",
        headers={**auth, "Content-Type": "text/plain"},
    )

    assert resp.status_code == 400


def test_post_primary_image_episode_not_supported(
    client: TestClient, seeded: dict
) -> None:
    """POST /Episodes/{id}/Images/Primary not supported → 405 or 501."""
    token = jf_login(client)
    auth = {"ApiKey": token}
    episode = seeded["episode"]
    from movieclaw_jellyfin.ids import episode_guid

    episode_guid_str = episode_guid(episode[0], episode[1], episode[2])

    resp = client.post(
        f"/Items/{episode_guid_str}/Images/Primary",
        content=b"fake image",
        headers={**auth, "Content-Type": "image/jpeg"},
    )

    # Accept both 405 Method Not Allowed and 501 Not Implemented
    assert resp.status_code in (405, 501), f"Expected 405/501, got {resp.status_code}"
