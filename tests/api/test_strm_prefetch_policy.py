"""Low-I/O scheduling policy, without any remote media reads."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from movieclaw_plugins.strm_prefetch.strm_prefetch import Config, _Prefetch


def scheduler(**config):
    ctx = SimpleNamespace(config=Config(**config), use=lambda key: SimpleNamespace(scoped=lambda ctx: None))
    p = _Prefetch(ctx)
    p.pending = AsyncMock(return_value={"items": [{"file_id": 1}], "total": 1, "next_cursor": None})
    p.backfill = AsyncMock()
    return p


@pytest.mark.asyncio
async def test_startup_and_files_added_do_not_schedule_library_reads():
    p = scheduler()
    await p.backfill_if_pending()
    await p.on_files_added(SimpleNamespace(files=[SimpleNamespace(strm=True)]))
    p.pending.assert_not_awaited()
    p.backfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_playback_blocks_on_demand_probe():
    from movieclaw_sdk.jobs import JobRetry
    p = scheduler()
    p.call = AsyncMock(return_value={"sessions": [{"id": "playing"}]})
    p.probe = AsyncMock(return_value={"status": "probed"})
    with pytest.raises(JobRetry):
        await p.run_legacy_item(SimpleNamespace(), {"file_id": 1})
    p.probe.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_failures_open_circuit_for_other_files():
    from movieclaw_sdk.jobs import JobRetry
    p = scheduler()
    p.call = AsyncMock(return_value={"sessions": [], "downloads": []})
    p.probe = AsyncMock(return_value={"status": "failed", "error": "mount timeout"})
    await p.run_legacy_item(SimpleNamespace(), {"file_id": 1})
    await p.run_legacy_item(SimpleNamespace(), {"file_id": 2})
    with pytest.raises(JobRetry):
        await p.run_legacy_item(SimpleNamespace(), {"file_id": 3})
    assert p.probe.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429])
async def test_real_http_status_opens_circuit_immediately(status):
    from movieclaw_sdk.jobs import JobRetry
    p = scheduler()
    p.call = AsyncMock(return_value={"sessions": [], "downloads": []})
    p.probe = AsyncMock(return_value={"status": "failed", "error": {"message_key": "player.strm.linkExpired", "params": {"status": status}}})
    await p.run_legacy_item(SimpleNamespace(), {"file_id": 1})
    with pytest.raises(JobRetry):
        await p.run_legacy_item(SimpleNamespace(), {"file_id": 2})
    assert p.probe.await_count == 1


def test_probe_api_preserves_machine_readable_failure():
    from movieclaw_api.api.routes.library_strm import StrmProbeView
    reason = {"message_key": "player.strm.linkExpired", "params": {"status": 429}}
    assert StrmProbeView(file_id=1, status="failed", error_ref=reason).model_dump()["error_ref"] == reason


@pytest.mark.asyncio
async def test_favorite_and_playback_never_prefetch_other_files():
    p = scheduler()
    p.jump = AsyncMock()
    await p.on_favorite(SimpleNamespace(media=SimpleNamespace(id=1, kind="movie"), season=1))
    await p.on_playback(SimpleNamespace(media=SimpleNamespace(id=1, kind="movie"), unit=SimpleNamespace(season=1, episode=1)))
    p.jump.assert_not_awaited()


@pytest.mark.asyncio
async def test_view_is_one_deduplicated_file_not_a_backfill():
    p = scheduler()
    p.jobs = SimpleNamespace(create=AsyncMock())
    event = SimpleNamespace(media=SimpleNamespace(id=1, kind="movie"), season=None, episode=None)
    for _ in range(5):
        await p.on_viewed(event)
    p.jobs.create.assert_awaited_once()
    assert p.jobs.create.call_args.kwargs["input"] == {"file_id": 1}
    p.backfill.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_view_never_queries_pending():
    p = scheduler(on_view=False)
    await p.on_viewed(SimpleNamespace(media=SimpleNamespace(id=1, kind="movie"), season=None, episode=None))
    p.pending.assert_not_awaited()
