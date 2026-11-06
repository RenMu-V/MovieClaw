"""Bounded native file I/O owned by a worker, including late-open cleanup.

Cancellation cannot interrupt a FUSE syscall. The request stops waiting immediately;
its worker retains its admission slot until that syscall returns and closes its FD.
Retries cannot grow an unbounded collection of abandoned native operations.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
from collections import Counter

_lock = threading.Lock()
_active: Counter[str] = Counter()
_MAX_WORKERS = 16
_MAX_PER_PATH = 2


class LocalStreamBusy(OSError):
    pass


class LocalStreamFile:
    def __init__(self, path):
        self.path = str(path)
        self._commands = queue.Queue()
        self._stopped = threading.Event()
        self._opened = concurrent.futures.Future()
        with _lock:
            if sum(_active.values()) >= _MAX_WORKERS or _active[self.path] >= _MAX_PER_PATH:
                raise LocalStreamBusy('Previous media I/O is still finishing')
            _active[self.path] += 1
        threading.Thread(target=self._run, name='media-file-io', daemon=True).start()

    def _run(self):
        try:
            with open(self.path, 'rb') as file:
                self._opened.set_result(None)
                while not self._stopped.is_set():
                    command = self._commands.get()
                    if command is None or self._stopped.is_set():
                        break
                    method, value, result = command
                    try:
                        result.set_result(getattr(file, method)(value))
                    except BaseException as exc:
                        result.set_exception(exc)
        except BaseException as exc:
            if not self._opened.done():
                self._opened.set_exception(exc)
        finally:
            with _lock:
                _active[self.path] -= 1
                if not _active[self.path]:
                    del _active[self.path]

    async def __aenter__(self):
        try:
            await asyncio.shield(asyncio.wrap_future(self._opened))
            return self
        except BaseException:
            self.close()
            raise

    async def __aexit__(self, *args):
        self.close()

    def close(self):
        self._stopped.set()
        self._commands.put(None)

    async def _call(self, method, value):
        result = concurrent.futures.Future()
        self._commands.put((method, value, result))
        return await asyncio.shield(asyncio.wrap_future(result))

    async def seek(self, offset):
        return await self._call('seek', offset)

    async def read(self, size):
        return await self._call('read', size)
