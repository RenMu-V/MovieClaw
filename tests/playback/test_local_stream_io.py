import asyncio
import os
import threading

import pytest

from movieclaw_playback.streaming import DisconnectAwareFileResponse


def test_blocked_open_disconnect_finishes_without_success_headers(tmp_path, monkeypatch):
    asyncio.run(_blocked_open_disconnect(tmp_path, monkeypatch))


async def _blocked_open_disconnect(tmp_path, monkeypatch):
    path = tmp_path / 'movie.mp4'
    path.write_bytes(b'video')
    entered, release = threading.Event(), threading.Event()
    real_open = open

    def blocked_open(name, *args, **kwargs):
        if str(name) == str(path):
            entered.set()
            release.wait(3)
        return real_open(name, *args, **kwargs)

    monkeypatch.setattr('builtins.open', blocked_open)
    disconnected = asyncio.Event()
    messages = []

    async def receive():
        await disconnected.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        messages.append(message)

    task = asyncio.create_task(DisconnectAwareFileResponse(path)(
        {'type': 'http', 'method': 'GET', 'headers': [], 'extensions': {}}, receive, send))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(.01)
        assert entered.is_set()
        disconnected.set()
        await asyncio.sleep(.1)
        assert task.done(), 'disconnect must not wait for native open'
        assert messages == [], 'success headers require readable first bytes'
    finally:
        release.set()
        await asyncio.wait_for(task, 4)


def test_blocked_read_retries_are_bounded_and_fds_close(tmp_path, monkeypatch):
    asyncio.run(_blocked_read_retries(tmp_path, monkeypatch))


async def _blocked_read_retries(tmp_path, monkeypatch):
    from movieclaw_playback.local_stream_io import LocalStreamBusy, LocalStreamFile, _active

    path = tmp_path / 'blocked.mp4'
    path.write_bytes(b'abcdef')
    release = threading.Event()
    entered = threading.Event()
    files = []
    reads = []
    real_open = open

    class BlockingFile:
        def __init__(self):
            self.file = real_open(path, 'rb', buffering=0)
            files.append(self.file)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
        def seek(self, offset):
            return self.file.seek(offset)
        def read(self, size):
            reads.append(size)
            entered.set()
            release.wait(3)
            return self.file.read(size)

    monkeypatch.setattr('builtins.open', lambda *a, **kw: BlockingFile())
    try:
        for _ in range(2):
            disconnected = asyncio.Event()
            messages = []
            async def receive():
                await disconnected.wait()
                return {'type': 'http.disconnect'}
            async def send(message):
                messages.append(message)
            task = asyncio.create_task(DisconnectAwareFileResponse(path)(
                {'type': 'http', 'method': 'GET', 'headers': [], 'extensions': {}}, receive, send))
            entered.clear()
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            assert entered.is_set()
            disconnected.set()
            await asyncio.wait_for(task, .3)
            assert messages == []
        with pytest.raises(LocalStreamBusy):
            LocalStreamFile(path)
        assert len(reads) == 2
    finally:
        release.set()
        for _ in range(100):
            if str(path) not in _active:
                break
            await asyncio.sleep(.01)
    assert str(path) not in _active
    assert all(f.closed for f in files)
    assert len(reads) == 2, 'stopped readers must never issue another read'

