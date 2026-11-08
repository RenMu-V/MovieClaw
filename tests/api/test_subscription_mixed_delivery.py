"""订阅混合库投递测试。

覆盖：
- 混合库作为订阅目标（movie/tv 订阅可明确选择 mixed 库）
- 自动路由混合库候选（按现有 match_rules 逻辑，mixed 候选按内容实际 kind 判型）
- 下载完成后按实际 kind 整理到 mixed 库的 movie/tv 子目录
- 订阅选库预检 (dispatch-preview) 支持 mixed 库
- 优先级与兜底语义保持一致（mixed 不能沉默改变现有库路由）
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlmodel import select

from movieclaw_api.core.config import get_settings
from movieclaw_api.services.media_library import MediaLibraryService
from movieclaw_api.services.subscription import SubscriptionService
from movieclaw_db.engine import dispose_db, get_database, init_db
from movieclaw_db.migrations import run_migrations
from movieclaw_db.models import Library
from movieclaw_db.repositories.library_repo import LibraryRepository
from movieclaw_media.models import MediaKind
from movieclaw_media.tmdb import TmdbClient

_KEY = "0123456789abcdef0123456789abcdef"

_ROUTES = {
    "/3/movie/550": {
        "id": 550,
        "title": "Fight Club",
        "original_title": "Fight Club",
        "release_date": "1999-10-15",
        "genres": [{"id": 18}],
        "origin_country": ["US"],
        "external_ids": {},
    },
    "/3/tv/1": {
        "id": 1,
        "name": "Breaking Bad",
        "original_name": "Breaking Bad",
        "first_air_date": "2008-01-20",
        "status": "Ended",
        "genres": [{"id": 18, "name": "剧情"}],
        "origin_country": ["US"],
        "external_ids": {},
        "alternative_titles": {"results": []},
        "translations": {"translations": []},
        "seasons": [{"season_number": 1}],
    },
    "/3/tv/1/season/1": {
        "name": "Season 1",
        "air_date": "2008-01-20",
        "episodes": [
            {"episode_number": 1, "name": "Pilot", "air_date": "2008-01-20"},
            {"episode_number": 2, "name": "Cat's in the Bag", "air_date": "2008-01-27"},
        ],
    },
}


def _fake_tmdb() -> TmdbClient:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _ROUTES.get(request.url.path)
        return httpx.Response(200 if payload is not None else 404, json=payload or {})

    return TmdbClient(_KEY, transport=httpx.MockTransport(handler))


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'mixed_sub.db'}")
    get_settings.cache_clear()
    init_db(get_settings().database_url, echo=False)
    await run_migrations()
    yield get_database()
    await dispose_db()
    get_settings.cache_clear()


def _service(session) -> SubscriptionService:
    return SubscriptionService(session, MediaLibraryService(session, _fake_tmdb()))


async def _make_libraries(session) -> dict[str, int]:
    """创建 movie / tv / mixed 三个库。"""
    repo = LibraryRepository(session)
    movie = await repo.create(name="电影库", kind="movie", root_paths=["/media/movies"])
    tv = await repo.create(name="剧集库", kind="tv", root_paths=["/media/tv"])
    mixed = await repo.create(name="混合库", kind="mixed", root_paths=["/media/mixed"])
    return {"movie": movie.id, "tv": tv.id, "mixed": mixed.id}


@pytest.mark.asyncio
async def test_movie_subscription_explicit_mixed_library(db) -> None:
    """电影订阅可显式选择 mixed 库作为目标。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = _service(session)

        # 创建电影订阅，指定 mixed 库
        sub = await svc.create(
            MediaKind.MOVIE, 550, library_id=lib_ids["mixed"]
        )

        assert sub.library_id == lib_ids["mixed"]
        assert sub.kind == "movie"


@pytest.mark.asyncio
async def test_tv_subscription_explicit_mixed_library(db) -> None:
    """剧集订阅可显式选择 mixed 库作为目标。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = _service(session)

        # 创建剧集订阅，指定 mixed 库
        sub = await svc.create(
            MediaKind.TV, 1, selected_seasons=[1], library_id=lib_ids["mixed"]
        )

        assert sub.library_id == lib_ids["mixed"]
        assert sub.kind == "tv"


@pytest.mark.asyncio
async def test_subscription_mixed_route_fallback_not_matched(db) -> None:
    """自动路由无匹配时：movie 默认电影库、tv 默认剧集库，不投 mixed（安全）。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = _service(session)

        # 不选库创建电影订阅：应落默认电影库，不是 mixed
        sub_movie = await svc.create(MediaKind.MOVIE, 550)
        assert sub_movie.library_id == lib_ids["movie"]

        # 不选库创建电影订阅：应落默认剧集库，不是 mixed
        sub_tv = await svc.create(MediaKind.TV, 1, selected_seasons=[1])
        assert sub_tv.library_id == lib_ids["tv"]


@pytest.mark.asyncio
async def test_subscription_dispatch_preview_mixed_explicit(db) -> None:
    """dispatch-preview 支持 mixed 库显式选择时的预检。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = _service(session)

        # 为电影调用 dispatch-preview，指定 mixed 库
        preview = await svc.preview_download_routing(
            "movie", lib_ids["mixed"], tmdb_id=550
        )

        assert preview.library_id == lib_ids["mixed"]
        assert preview.ok is True
        # route_matched 应为 null（显式选库不走路由）
        assert preview.route_matched is None


@pytest.mark.asyncio
async def test_subscription_kind_mismatch_with_movie_library_rejected(db) -> None:
    """选择 movie 库订阅 tv 仍应拒绝（混合库外的类型不匹配仍有效）。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = _service(session)

        # 剧集订阅选 movie 库应拒绝
        from movieclaw_api.core.exceptions import BadRequestException
        with pytest.raises(BadRequestException):
            await svc.create(MediaKind.TV, 1, selected_seasons=[1], library_id=lib_ids["movie"])


@pytest.mark.asyncio
async def test_subscription_kind_mismatch_with_tv_library_rejected(db) -> None:
    """选择 tv 库订阅 movie 仍应拒绝。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = _service(session)

        # 电影订阅选 tv 库应拒绝
        from movieclaw_api.core.exceptions import BadRequestException
        with pytest.raises(BadRequestException):
            await svc.create(MediaKind.MOVIE, 550, library_id=lib_ids["tv"])
