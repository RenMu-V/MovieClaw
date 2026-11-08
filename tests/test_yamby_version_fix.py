"""测试 Yamby 客户端获取 10.10.7 版本号的修复。

Yamby 不支持 12.1.0 版本号，导致它回退到 Emby 模式，识别不出混合库
（CollectionType=folders）。修复方案：把 yamby 加入 _LEGACY_CLIENT_MARKERS，
让它拿到 10.10.7 版本号，与 Infuse/VidHub 相同。
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import Request

from movieclaw_jellyfin.authhdr import AuthorizationInfo
from movieclaw_jellyfin.identity import (
    LEGACY_REPORTED_VERSION,
    REPORTED_VERSION,
    reported_version,
)


def create_mock_request(user_agent: str = "", client: str = "") -> Request:
    """创建模拟的 FastAPI Request 对象。"""
    request = Mock(spec=Request)
    request.headers = {"User-Agent": user_agent}
    return request


@patch("movieclaw_jellyfin.identity.read_authorization")
def test_yamby_gets_legacy_version(mock_read_auth):
    """Yamby 客户端应该拿到 10.10.7 版本号。"""
    # Yamby 的真实 User-Agent 格式（基于 Android 客户端）
    mock_read_auth.return_value = AuthorizationInfo(client="Yamby")
    request = create_mock_request(user_agent="Yamby/1.2.3 (Android)")
    version = reported_version(request)
    assert version == LEGACY_REPORTED_VERSION, (
        f"Yamby 应该拿到 {LEGACY_REPORTED_VERSION}，实际拿到 {version}"
    )


@patch("movieclaw_jellyfin.identity.read_authorization")
def test_yamby_case_insensitive(mock_read_auth):
    """Yamby 标识检测应该不区分大小写。"""
    # 测试不同的大小写组合
    for ua in ["yamby", "Yamby", "YAMBY", "YaMbY"]:
        mock_read_auth.return_value = AuthorizationInfo(client="")
        request = create_mock_request(user_agent=ua)
        version = reported_version(request)
        assert version == LEGACY_REPORTED_VERSION, (
            f"User-Agent={ua} 应该拿到 {LEGACY_REPORTED_VERSION}，实际拿到 {version}"
        )


@patch("movieclaw_jellyfin.identity.read_authorization")
def test_yamby_in_client_field(mock_read_auth):
    """Authorization Client=Yamby 也应该触发 legacy 版本。"""
    mock_read_auth.return_value = AuthorizationInfo(client="Yamby")
    request = create_mock_request(user_agent="")
    version = reported_version(request)
    assert version == LEGACY_REPORTED_VERSION


@patch("movieclaw_jellyfin.identity.read_authorization")
def test_infuse_still_gets_legacy_version(mock_read_auth):
    """确保 Infuse 仍然拿到 10.10.7（回归测试）。"""
    mock_read_auth.return_value = AuthorizationInfo(client="Infuse-Direct")
    request = create_mock_request(user_agent="Infuse-Direct/7.5")
    version = reported_version(request)
    assert version == LEGACY_REPORTED_VERSION


@patch("movieclaw_jellyfin.identity.read_authorization")
def test_vidhub_still_gets_legacy_version(mock_read_auth):
    """确保 VidHub 仍然拿到 10.10.7（回归测试）。"""
    mock_read_auth.return_value = AuthorizationInfo(client="VidHub")
    request = create_mock_request(user_agent="VidHub/1.0")
    version = reported_version(request)
    assert version == LEGACY_REPORTED_VERSION


@patch("movieclaw_jellyfin.identity.read_authorization")
def test_other_clients_get_default_version(mock_read_auth):
    """其他客户端应该拿到 12.1.0 默认版本。"""
    test_cases = [
        ("Jellyfin Android/1.8.12", "Jellyfin Android"),
        ("Mozilla/5.0", "Web"),
        ("", ""),  # 空客户端
    ]
    for user_agent, client in test_cases:
        mock_read_auth.return_value = AuthorizationInfo(client=client)
        request = create_mock_request(user_agent=user_agent)
        version = reported_version(request)
        assert version == REPORTED_VERSION, (
            f"UA={user_agent}, Client={client} 应该拿到 {REPORTED_VERSION}，实际拿到 {version}"
        )
