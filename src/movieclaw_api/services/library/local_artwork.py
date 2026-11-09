"""Image-only TMDB fallback; never promotes a local identity or merges metadata.

Called by the existing bounded scan/watch asset workers, after sidecar ingestion.
Negative results live alongside native asset provenance and survive restarts.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path

from movieclaw_api.services.library.nfo import read_entry_identity
from movieclaw_api.services.library.resolve import normalize_title

logger = logging.getLogger(__name__)
_GATE = asyncio.Semaphore(2)
# Striped locks bound memory and coalesce simultaneous scan/watch/refresh calls.
_LOCKS = [asyncio.Lock() for _ in range(64)]
_TAG = re.compile(r"(?:\{tmdb[-=](\d+)\}|\[tmdb[-=](\d+)\])", re.I)


def trusted_id(video: Path, kind: str) -> int | None:
    """Only entry-level typed NFO IDs; contradictory explicit tags fail closed."""
    paths = [video.with_suffix('.nfo'), video.parent / ('tvshow.nfo' if kind == 'tv' else 'movie.nfo')]
    identities = [read_entry_identity(p) for p in paths]
    identities = [i for i in identities if i is not None]
    if any(i.kind.value != kind for i in identities):
        return None
    ids = {i.tmdb_id for i in identities if i.tmdb_id}
    tags = {int(a or b) for a, b in _TAG.findall(str(video))}
    if len(ids) != 1 or (tags and tags != ids):
        return None
    return next(iter(ids))


async def ensure_remote_images(item_id: int, video: Path, library, *, force: bool = False) -> None:
    """Fill absent unlocked poster/backdrop only, through native network/codec policy."""
    from movieclaw_api.services import media_scrape as scrape
    from movieclaw_api.services.media_discover import get_tmdb_client
    from movieclaw_db.models import MediaItem, MediaSource, utcnow
    from movieclaw_db.repositories.media_repo import MediaItemRepository

    # A local-only library is an explicit offline choice, even with typed NFO IDs.
    if library.source != 'tmdb':
        return
    async with _LOCKS[item_id % len(_LOCKS)]:
        async with scrape.get_database().session() as session:
            item = await session.get(MediaItem, item_id)
            if item is None or item.source != MediaSource.LOCAL or item.kind not in ('movie', 'tv'):
                return
            meta = await MediaItemRepository(session).get_metadata(item_id)
            if meta is None:
                return
            missing = [k for k in ('poster', 'backdrop') if not getattr(meta, f'{k}_file') and not getattr(meta, f'{k}_locked')]
            if not missing:
                return
            tmdb_id = await asyncio.to_thread(trusted_id, video, item.kind)
            if tmdb_id is None:
                return
            item_dir = scrape.assets_root() / str(item_id)
            state_file = item_dir / 'local-artwork-retry.json'
            try:
                state = json.loads(await asyncio.to_thread(state_file.read_text))
            except (OSError, ValueError):
                state = {}
            identity = f'{item.kind}:{tmdb_id}'
            if not force and state.get('identity') == identity and state.get('retry_at', 0) > time.time():
                return
            # Mark before network, so crashes also back off. Manual refresh can retry.
            retry = {'identity': identity, 'retry_at': time.time() + 86400}
            await asyncio.to_thread(scrape._atomic_write, state_file, json.dumps(retry).encode())
            try:
                async with _GATE:
                    from movieclaw_api.services.scrape_config import effective_languages
                    setting = await scrape.scrape_setting_for_item(session, item)
                    profile = await get_tmdb_client().get(f'{item.kind}/{tmdb_id}', {'language': effective_languages(setting)[0]})
                    names = {normalize_title(profile.get(k) or '') for k in ('title', 'original_title', 'name', 'original_name')}
                    local_names = {normalize_title(v) for v in (item.title, item.original_title) if v}
                    date = profile.get('release_date' if item.kind == 'movie' else 'first_air_date') or ''
                    year = int(date[:4]) if date[:4].isdigit() else None
                    if profile.get('id') != tmdb_id or not (names & local_names) or (item.year and year != item.year):
                        return
                    sources = await asyncio.to_thread(scrape._load_asset_sources, item_dir)
                    setting = await scrape.scrape_setting_for_item(session, item)
                    poster_size, backdrop_size, _ = scrape._asset_sizes(setting)
                    base = scrape.effective_tmdb_image_base_url().rstrip('/')
                    for key in missing:
                        path = profile.get(f'{key}_path')
                        # Never accept arbitrary absolute URLs or traversal from provider data.
                        if not isinstance(path, str) or not re.fullmatch(r'/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png)', path):
                            continue
                        dest = item_dir / f'{key}.jpg'
                        # Existing unreferenced bytes may be manually managed; never clobber.
                        if dest.exists():
                            continue
                        rel = await scrape._sync_asset(base, poster_size if key == 'poster' else backdrop_size,
                                                       path, dest, None, sources, key, tally=scrape.AssetTally())
                        if rel:
                            setattr(meta, f'{key}_file', rel)
                            if key == 'poster':
                                from movieclaw_api.services.library.thumbs import _image_size, blur_placeholder
                                size = await asyncio.to_thread(_image_size, dest)
                                if size:
                                    meta.poster_width, meta.poster_height = size
                                meta.poster_blur = await asyncio.to_thread(blur_placeholder, dest)
                    await asyncio.to_thread(scrape._save_asset_sources, item_dir, sources)
                    meta.updated_at = utcnow()
                    session.add(meta)
                    await session.commit()
            except Exception:
                logger.warning('Local artwork fallback failed for #%s; backed off', item_id, exc_info=True)
