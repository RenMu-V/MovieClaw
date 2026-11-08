#!/usr/bin/env python3
"""简单的独立测试脚本：验证 Yamby 是否在 LEGACY_CLIENT_MARKERS 中。

这个脚本不依赖 pytest 或其他复杂依赖，只检查源码是否包含修复。
"""

import re
import sys
from pathlib import Path


def test_yamby_in_legacy_markers():
    """检查 identity.py 中 _LEGACY_CLIENT_MARKERS 是否包含 'yamby'。"""
    identity_file = Path(__file__).parent / "src" / "movieclaw_jellyfin" / "identity.py"
    
    if not identity_file.exists():
        print(f"❌ 找不到文件: {identity_file}")
        return False
    
    content = identity_file.read_text()
    
    # 查找 _LEGACY_CLIENT_MARKERS 的定义
    pattern = r'_LEGACY_CLIENT_MARKERS\s*=\s*\((.*?)\)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("❌ 找不到 _LEGACY_CLIENT_MARKERS 定义")
        return False
    
    markers_str = match.group(1)
    print(f"找到 _LEGACY_CLIENT_MARKERS = ({markers_str})")
    
    # 检查是否包含 "yamby"
    if '"yamby"' in markers_str or "'yamby'" in markers_str:
        print("✅ 已包含 'yamby' 在 _LEGACY_CLIENT_MARKERS 中")
        return True
    else:
        print("❌ _LEGACY_CLIENT_MARKERS 中缺少 'yamby'")
        print("   当前值:", markers_str.strip())
        print("   应该包含: 'yamby'")
        return False


if __name__ == "__main__":
    success = test_yamby_in_legacy_markers()
    sys.exit(0 if success else 1)
