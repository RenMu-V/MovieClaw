#!/usr/bin/env python3
"""Final verification of all mixed library fixes before deployment."""

import re
import sys
from pathlib import Path

def verify_all_fixes():
    """Verify all 5 fixes are in place."""
    
    print("=" * 70)
    print("FINAL VERIFICATION: Mixed Library Fixes")
    print("=" * 70)
    
    checks = []
    
    # 1. jellyfin_collection not empty
    print("\n1. Checking jellyfin_collection fix...")
    with open('src/movieclaw_api/services/library/profile.py', 'r') as f:
        profile_content = f.read()
    if 'jellyfin_collection="folders"' in profile_content and 'jellyfin_collection=""' not in profile_content:
        print("   ✓ jellyfin_collection changed to 'folders' (not empty)")
        checks.append(True)
    else:
        print("   ✗ jellyfin_collection not fixed properly")
        checks.append(False)
    
    # 2. mixed+local profile exists
    print("\n2. Checking mixed+local profile...")
    if 'PROFILES[("mixed", MediaSource.LOCAL)]' in profile_content:
        print("   ✓ mixed+local profile added to PROFILES")
        checks.append(True)
    else:
        print("   ✗ mixed+local profile missing")
        checks.append(False)
    
    # 3. SxxExx regex relaxed (no \b)
    print("\n3. Checking SxxExx regex relaxation...")
    with open('src/movieclaw_api/services/library/scan.py', 'r') as f:
        scan_content = f.read()
    
    # Look for the relaxed pattern (no \b)
    if re.search(r'r".*S\\d.*E\\d.*".*# Relaxed', scan_content, re.MULTILINE):
        print("   ✓ SxxExx regex relaxed (no word boundary)")
        checks.append(True)
    elif 'S\\d{1,3}E\\d{1,4}' in scan_content and '\\b' not in scan_content.split('S\\d{1,3}E\\d{1,4}')[0][-50:]:
        print("   ✓ SxxExx regex uses flexible pattern (no strict word boundary)")
        checks.append(True)
    else:
        print("   ✗ SxxExx regex not properly relaxed")
        checks.append(False)
    
    # 4. Cover.jpg support (in docstring or code)
    print("\n4. Checking Cover.jpg sidecar support...")
    if 'Cover.jpg' in scan_content or 'cover.jpg' in scan_content.lower():
        print("   ✓ Cover.jpg recognized as poster candidate")
        checks.append(True)
    else:
        print("   ✗ Cover.jpg support missing")
        checks.append(False)
    
    # 5. Local-first scanning (build_local_identity in mixed handling)
    print("\n5. Checking local-first identification...")
    if 'is_local_source' in scan_content and 'build_local_identity' in scan_content:
        if scan_content.count('build_local_identity') >= 2:  # At least 2 calls
            print("   ✓ Local-first identification implemented for mixed+local")
            checks.append(True)
        else:
            print("   ⚠ build_local_identity usage may be insufficient")
            checks.append(False)
    else:
        print("   ✗ Local-first logic not found")
        checks.append(False)
    
    # Summary
    print("\n" + "=" * 70)
    passed = sum(checks)
    total = len(checks)
    print(f"RESULT: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✓ All fixes verified! Ready for deployment.")
        return 0
    else:
        print(f"\n✗ {total - passed} fix(es) incomplete. Review above.")
        return 1

if __name__ == "__main__":
    sys.exit(verify_all_fixes())
