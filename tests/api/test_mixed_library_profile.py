"""
Test mixed library profile support.

Issue 1: profile_of_values('mixed', 'local') should work (currently throws BadRequestException)
Issue 2: jellyfin_collection should be a valid Jellyfin CollectionType (not empty string)
"""

import pytest
from movieclaw_api.services.library.profile import (
    profile_for,
    profile_of_values,
    profile_for_key,
    PROFILES,
    LibraryKind,
)
from movieclaw_api.exceptions import BadRequestException
from movieclaw_db.models.media_item import MediaSource
from movieclaw_media.models import MediaKind


class TestMixedProfileBasics:
    """Basic profile retrieval tests for mixed library."""

    def test_mixed_tmdb_exists_in_profiles(self):
        """mixed+tmdb profile must exist in PROFILES table."""
        key = ("mixed", MediaSource.TMDB)
        assert key in PROFILES
        profile = PROFILES[key]
        assert profile.kind == LibraryKind.MIXED
        assert profile.source == MediaSource.TMDB

    def test_mixed_tmdb_via_profile_for(self):
        """profile_for('mixed', 'tmdb') should return valid profile."""
        profile = profile_for("mixed", MediaSource.TMDB)
        assert profile.kind == LibraryKind.MIXED
        assert profile.source == MediaSource.TMDB
        assert profile.subscribable is True

    def test_mixed_tmdb_via_profile_for_key(self):
        """profile_for_key('mixed', 'tmdb') should return valid profile."""
        profile = profile_for_key("mixed", MediaSource.TMDB)
        assert profile is not None
        assert profile.kind == LibraryKind.MIXED
        assert profile.source == MediaSource.TMDB


class TestMixedLocalProfileIssue1Fixed:
    """Tests verifying that Issue 1 (mixed+local support) is now fixed.
    
    These were previously raising BadRequestException but should now work.
    """

    def test_mixed_local_via_profile_for_now_works(self):
        """profile_for('mixed', 'local') now returns valid profile instead of raising."""
        # Previously: with pytest.raises(BadRequestException)
        # Now: should work normally
        profile = profile_for("mixed", MediaSource.LOCAL)
        assert profile is not None
        assert profile.kind == LibraryKind.MIXED
        assert profile.source == MediaSource.LOCAL

    def test_mixed_local_via_profile_of_values_now_works(self):
        """profile_of_values('mixed', 'local') now returns valid profile instead of raising."""
        # Previously: with pytest.raises(BadRequestException)
        # Now: should work normally
        profile = profile_of_values("mixed", MediaSource.LOCAL)
        assert profile is not None
        assert profile.kind == LibraryKind.MIXED
        assert profile.source == MediaSource.LOCAL


class TestJellyfinCollectionTypeIssue2Fixed:
    """Tests verifying that Issue 2 (jellyfin_collection empty string) is now fixed.
    
    Previously jellyfin_collection was empty string, which causes Jellyfin/Yamby
    to hide the library. Now it should have a valid CollectionType.
    """

    def test_mixed_tmdb_jellyfin_collection_not_empty(self):
        """mixed+tmdb jellyfin_collection should not be empty string."""
        profile = profile_for("mixed", MediaSource.TMDB)
        assert profile.jellyfin_collection != ""
        assert profile.jellyfin_collection is not None
        assert profile.jellyfin_collection == "folders"

    def test_mixed_tmdb_jellyfin_collection_is_valid_type(self):
        """jellyfin_collection should be a valid Jellyfin CollectionType value.
        
        Valid values based on Jellyfin source code:
        movies, tvshows, music, musicvideos, trailers, homevideos, boxsets,
        books, photos, livetv, playlists, folders, unknown
        """
        valid_types = {
            "movies", "tvshows", "music", "musicvideos", "trailers",
            "homevideos", "boxsets", "books", "photos", "livetv",
            "playlists", "folders", "unknown"
        }
        profile = profile_for("mixed", MediaSource.TMDB)
        assert profile.jellyfin_collection in valid_types
        # Should not be empty string, as it hides the library
        assert profile.jellyfin_collection != ""

    def test_mixed_local_jellyfin_collection_not_empty(self):
        """mixed+local jellyfin_collection should also not be empty string."""
        profile = profile_for("mixed", MediaSource.LOCAL)
        assert profile.jellyfin_collection != ""
        assert profile.jellyfin_collection == "folders"


class TestJellyfinExposedAndCapabilities:
    """Test that mixed library has correct Jellyfin capabilities."""

    def test_mixed_tmdb_is_jellyfin_exposed(self):
        """mixed+tmdb should be exposed to Jellyfin."""
        profile = profile_for("mixed", MediaSource.TMDB)
        assert profile.jellyfin_exposed is True

    def test_mixed_tmdb_playable(self):
        """mixed+tmdb should be playable."""
        profile = profile_for("mixed", MediaSource.TMDB)
        assert profile.playable is True

    def test_mixed_tmdb_jellyfin_type_movie(self):
        """
        mixed library's jellyfin_type should be 'Movie' (default like movie+tmdb).
        
        Individual items will have correct type (Movie/Series/Season/Episode)
        based on their actual media_item.kind.
        """
        profile = profile_for("mixed", MediaSource.TMDB)
        assert profile.jellyfin_type == "Movie"




class TestMixedLocalExposureAndCapabilities:
    """Test that mixed+local library has correct Jellyfin capabilities."""

    def test_mixed_local_is_jellyfin_exposed(self):
        """mixed+local should be exposed to Jellyfin."""
        profile = profile_of_values("mixed", MediaSource.LOCAL)
        assert profile.jellyfin_exposed is True

    def test_mixed_local_playable(self):
        """mixed+local should be playable."""
        profile = profile_of_values("mixed", MediaSource.LOCAL)
        assert profile.playable is True

    def test_mixed_local_has_valid_jellyfin_collection(self):
        """mixed+local should have valid jellyfin_collection."""
        profile = profile_of_values("mixed", MediaSource.LOCAL)
        assert profile.jellyfin_collection != ""
        assert profile.jellyfin_collection in {
            "movies", "tvshows", "homevideos", "folders", "unknown"
        }

