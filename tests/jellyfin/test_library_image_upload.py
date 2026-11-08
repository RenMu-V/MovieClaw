"""Library Primary upload uses the native durable cover, not media metadata."""

import base64
import io

from PIL import Image

from jellyfin.helpers import jf_login
from movieclaw_jellyfin.ids import library_guid


def picture():
    out = io.BytesIO()
    Image.new("RGB", (90, 60), (25, 100, 180)).save(out, "PNG")
    return out.getvalue()


def test_library_primary_upload(client, seeded, monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "uploads"))
    from movieclaw_api.core.config import get_settings

    get_settings.cache_clear()
    guid = library_guid(seeded["movie_lib"])
    token = jf_login(client)
    headers = {"X-Emby-Token": token, "Content-Type": "image/png"}
    url = f"/emby/Items/{guid}/Images/Primary"
    old = client.get(url).headers["etag"]
    response = client.post(url, content=picture(), headers=headers)
    assert response.status_code == 204, response.text
    jf = client.get(url, headers=headers)
    web = client.get(f"/api/v1/libraries/{seeded['movie_lib']}/cover")
    assert jf.content == web.content
    assert jf.headers["etag"] != old
    image = Image.open(io.BytesIO(jf.content))
    assert image.size == (90, 60)
    pixel = image.convert("RGB").getpixel((45, 30))
    assert all(abs(a - b) < 5 for a, b in zip(pixel, (25, 100, 180), strict=True))
    from movieclaw_api.services.library.cover import has_custom_cover

    assert has_custom_cover(seeded["movie_lib"])
    assert client.get(url).content == jf.content


def test_upload_boundaries(client, seeded, monkeypatch, tmp_path):
    from movieclaw_api.core.config import get_settings
    from movieclaw_jellyfin.ids import item_guid

    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    token = jf_login(client)
    headers = {"X-Emby-Token": token, "Content-Type": "image/png"}
    url = f"/emby/Items/{library_guid(seeded['movie_lib'])}/Images/Primary"
    assert client.post(url, content=picture()).status_code == 401
    member = {"username": "covermember", "password": "cover-pass-123"}
    assert client.post("/api/v1/members", json=member).status_code == 200
    login = client.post(
        "/Users/AuthenticateByName",
        json={"Username": member["username"], "Pw": member["password"]},
        headers={
            "Authorization": (
                'MediaBrowser Client="CoverTest", DeviceId="cover-member", '
                'Device="Test", Version="1"'
            )
        },
    )
    assert login.status_code == 200
    member_headers = {**headers, "X-Emby-Token": login.json()["AccessToken"]}
    assert client.post(url, content=picture(), headers=member_headers).status_code == 403
    assert client.post(
        f"/Items/{item_guid(seeded['movie'])}/Images/Primary", content=picture(), headers=headers
    ).status_code in (405, 501)
    assert client.post(url + "/1", content=picture(), headers=headers).status_code == 400
    assert client.post(url + "?ImageIndex=1", content=picture(), headers=headers).status_code == 400
    assert (
        client.post(
            url.replace(library_guid(seeded["movie_lib"]), library_guid(99999)),
            content=picture(),
            headers=headers,
        ).status_code
        == 404
    )
    for data in (b"", b"invalid", b"X" * (10 * 1024 * 1024 + 1)):
        assert client.post(url, content=data, headers=headers).status_code in (400, 413)
    from movieclaw_api.services.library import cover

    monkeypatch.setattr(cover, "MAX_UPLOAD_PIXELS", 100)
    assert client.post(url, content=picture(), headers=headers).status_code == 400


def test_base64_library_upload(client, seeded, monkeypatch, tmp_path):
    from movieclaw_api.core.config import get_settings

    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    url = f"/Items/{library_guid(seeded['movie_lib'])}/Images/Primary/0"
    headers = {"X-Emby-Token": jf_login(client), "Content-Type": "image/png; charset=utf-8"}
    response = client.post(url, content=base64.b64encode(picture()), headers=headers)
    assert response.status_code == 204, response.text
    assert Image.open(io.BytesIO(client.get(url).content)).size == (90, 60)
