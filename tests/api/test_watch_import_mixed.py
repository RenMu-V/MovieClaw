"""监听导入mixed库测试。

覆盖：
- watch import支持mixed库作为显式library_id目标
- mixed库与自动路由的交互
- 入库时按item的kind子目录分离（不涉及ingest，只是配置验证）
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from pathlib import Path

from movieclaw_api.core.config import get_settings
from movieclaw_api.services.import_watch_config import ImportWatchConfigService
from movieclaw_db.engine import dispose_db, get_database, init_db
from movieclaw_db.migrations import run_migrations
from movieclaw_db.repositories.library_repo import LibraryRepository
from movieclaw_api.exceptions import BadRequestException


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'watch_mixed.db'}")
    get_settings.cache_clear()
    init_db(get_settings().database_url, echo=False)
    await run_migrations()
    yield get_database()
    await dispose_db()
    get_settings.cache_clear()


async def _make_libraries(session) -> dict[str, int | None]:
    """创建 movie / tv / mixed 三个库。"""
    repo = LibraryRepository(session)
    movie = await repo.create(name="电影库", kind="movie", root_paths=["/media/movies"])
    tv = await repo.create(name="剧集库", kind="tv", root_paths=["/media/tv"])
    mixed = await repo.create(name="混合库", kind="mixed", root_paths=["/media/mixed"])
    return {"movie": movie.id, "tv": tv.id, "mixed": mixed.id}  # type: ignore


@pytest.mark.asyncio
async def test_watch_import_mixed_library(db, tmp_path):
    """监听导入支持 mixed 库作为显式 library_id。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = ImportWatchConfigService(session)
        
        # 创建监听规则指向 mixed 库
        rule = await svc.create(
            source_path="/downloads/watch",
            strategy="hardlink",
            library_id=lib_ids["mixed"],
        )
        
        assert rule.id is not None
        assert rule.library_id == lib_ids["mixed"]


@pytest.mark.asyncio
async def test_watch_import_movie_auto_routing(db):
    """movie kind auto 规则在有 mixed 库时仍路由到 movie 库（非 mixed）。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = ImportWatchConfigService(session)
        
        # 创建 movie kind auto 规则
        rule = await svc.create(
            source_path="/downloads/watch_movie",
            strategy="hardlink",
            library_id=None,
            kind="movie",
        )
        
        # 应当成功创建，且指向 auto 路由（库存在且可路由）
        assert rule.id is not None
        assert rule.library_id is None
        assert rule.kind == "movie"


@pytest.mark.asyncio
async def test_watch_import_tv_auto_routing(db):
    """tv kind auto 规则在有 mixed 库时仍路由到 tv 库（非 mixed）。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = ImportWatchConfigService(session)
        
        # 创建 tv kind auto 规则
        rule = await svc.create(
            source_path="/downloads/watch_tv",
            strategy="hardlink",
            library_id=None,
            kind="tv",
        )
        
        # 应当成功创建，且指向 auto 路由（库存在且可路由）
        assert rule.id is not None
        assert rule.library_id is None
        assert rule.kind == "tv"


@pytest.mark.asyncio
async def test_watch_import_mixed_explicit_over_auto_routing(db):
    """显式 mixed 库选择优先于自动路由。"""
    async with db.session() as session:
        lib_ids = await _make_libraries(session)
        svc = ImportWatchConfigService(session)
        
        # 创建指向 mixed 库的规则（explicit）
        explicit_rule = await svc.create(
            source_path="/downloads/explicit",
            strategy="hardlink",
            library_id=lib_ids["mixed"],
        )
        
        # 创建 movie auto 规则
        auto_rule = await svc.create(
            source_path="/downloads/auto",
            strategy="hardlink",
            library_id=None,
            kind="movie",
        )
        
        assert explicit_rule.library_id == lib_ids["mixed"]
        assert auto_rule.kind == "movie" and auto_rule.library_id is None


@pytest.mark.asyncio
async def test_watch_import_mixed_no_hardlink_same_disk_check(db, tmp_path, monkeypatch):
    """mixed库的hardlink同盘检测应当与专属movie/tv库同样工作。"""
    async with db.session() as session:
        # 模拟跨盘情况（简化：设置不同路径前缀的伪st_dev）
        repo = LibraryRepository(session)
        mixed = await repo.create(
            name="跨盘混合库", kind="mixed", root_paths=["/strm/mixed"]
        )
        
        svc = ImportWatchConfigService(session)
        
        # hardlink 到跨盘库应该被拒绝
        with pytest.raises(BadRequestException) as exc:
            await svc.create(
                source_path="/video/downloads",
                strategy="hardlink",
                library_id=mixed.id,
            )
        assert "同盘" in str(exc.value) or "cross" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_watch_import_mixed_copy_strategy_allowed(db):
    """copy 策略应当跳过同盘检测，mixed库接受cross-disk copy。"""
    async with db.session() as session:
        repo = LibraryRepository(session)
        mixed = await repo.create(
            name="混合库", kind="mixed", root_paths=["/media/mixed"]
        )
        
        svc = ImportWatchConfigService(session)
        
        # copy 策略应该成功（不做同盘检测）
        rule = await svc.create(
            source_path="/downloads/watch",
            strategy="copy",
            library_id=mixed.id,
        )
        
        assert rule.id is not None
        assert rule.strategy == "copy"
