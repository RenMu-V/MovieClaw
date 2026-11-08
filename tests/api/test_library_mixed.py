"""Mixed is a library scope, never a TMDB media namespace."""
from pathlib import Path

from movieclaw_api.schemas.library import LibraryPayload
from movieclaw_api.services.library.profile import library_kind_options, profile_for
from movieclaw_media.models import MediaKind


def test_mixed_wizard_has_explicit_copy():
    root = Path(__file__).parents[2]
    text = (root / "apps/web/components/library-form-dialog.tsx").read_text()
    assert 'mixed: {' in text
    assert "电影与剧集同库" in text


def test_mixed_library_payload_and_capabilities():
    payload = LibraryPayload(name="混合内容测试", kind="mixed", root_paths=["/fixture"])
    assert payload.kind.value == "mixed"
    profile = profile_for("mixed")
    assert profile.scraped and profile.playable and profile.jellyfin_exposed
    assert profile.jellyfin_collection == ""
    assert "mixed" in {p["kind"] for p in library_kind_options()}
    assert "mixed" not in {kind.value for kind in MediaKind}
