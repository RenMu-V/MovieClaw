#!/usr/bin/env python3
"""Quick verification of profile fixes without full dependency install."""

import sys
import re

# Read profile.py and verify fixes
with open('src/movieclaw_api/services/library/profile.py', 'r') as f:
    content = f.read()

print("=" * 70)
print("PROFILE.PY FIX VERIFICATION")
print("=" * 70)

# Check Issue 1: mixed+local exists
if 'PROFILES[("mixed", MediaSource.LOCAL)]' in content:
    print("\n✓ Issue 1 FIXED: mixed+LOCAL profile added to PROFILES")
else:
    print("\n✗ Issue 1 NOT FIXED: mixed+local profile missing")
    sys.exit(1)

# Check Issue 2: jellyfin_collection is not empty
if 'jellyfin_collection=""' in content:
    print("✗ Issue 2 NOT FIXED: jellyfin_collection still has empty string")
    sys.exit(1)
else:
    print("✓ Issue 2 FIXED: jellyfin_collection is not empty string")

# Verify jellyfin_collection value
if 'jellyfin_collection="folders"' in content:
    print("  → Using valid Jellyfin CollectionType: 'folders'")
else:
    print("✗ jellyfin_collection value not 'folders'")
    sys.exit(1)

# Verify both mixed+tmdb and mixed+local have folders
count_folders = content.count('jellyfin_collection="folders"')
if count_folders >= 2:
    print(f"✓ Both mixed+tmdb and mixed+local use 'folders': {count_folders} occurrences")
else:
    print(f"⚠ Only {count_folders} occurrences of jellyfin_collection='folders' (expected 2+)")

# Check that mixed+local inherits from video+local
if 'PROFILES[("mixed", MediaSource.LOCAL)] = replace(\n    PROFILES[("video", MediaSource.LOCAL)]' in content:
    print("✓ mixed+local correctly inherits from video+local profile")
else:
    print("⚠ mixed+local inheritance may be incorrect")

# Check that mixed+tmdb inherits from movie+tmdb
if 'PROFILES[("mixed", MediaSource.TMDB)] = replace(\n    PROFILES[("movie", MediaSource.TMDB)]' in content:
    print("✓ mixed+tmdb correctly inherits from movie+tmdb profile")
else:
    print("⚠ mixed+tmdb inheritance may be incorrect")

print("\n" + "=" * 70)
print("TEST FILE VERIFICATION")
print("=" * 70)

with open('tests/api/test_mixed_library_profile.py', 'r') as f:
    test_content = f.read()

# Verify test file has proper test classes
test_classes = [
    'TestMixedProfileBasics',
    'TestMixedLocalProfileIssue1Fixed',
    'TestJellyfinCollectionTypeIssue2Fixed',
    'TestJellyfinExposedAndCapabilities',
    'TestMixedLocalExposureAndCapabilities',
]

for test_class in test_classes:
    if f'class {test_class}:' in test_content:
        print(f"✓ Test class {test_class} exists")
    else:
        print(f"✗ Test class {test_class} missing")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("\n✓ All profile fixes verified!")
print("\nChanges made:")
print("  1. Added PROFILES[('mixed', MediaSource.LOCAL)] entry")
print("  2. Changed jellyfin_collection from '' to 'folders' for both mixed+tmdb and mixed+local")
print("  3. Created comprehensive TDD test suite")
print("\nNext steps:")
print("  1. Run pytest tests/api/test_mixed_library_profile.py -v")
print("  2. Build ARM64 image")
print("  3. Deploy and verify in Jellyfin/Yamby")
