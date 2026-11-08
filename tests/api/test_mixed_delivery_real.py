"""Real SQLite, NFO identity, ffprobe and filesystem transfer regression tests."""
import os
import subprocess

import pytest
from sqlmodel import select

from tests.api.test_library_ingest import db  # noqa: F401
from movieclaw_api.services.library import ingest
from movieclaw_api.services.library.routing import RoutingFacts, route
from movieclaw_api.services.import_watch_config import ImportWatchConfigService
from movieclaw_db.models import Library, ImportWatch, MediaItem, LibraryFile, IngestEntry, IngestStatus
from movieclaw_db.repositories.library_repo import LibraryRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["hardlink", "copy"])
async def test_mixed_real_transfer(db, tmp_path, strategy):
    root, watch = tmp_path / "mixed", tmp_path / "watch"
    root.mkdir()
    watch.mkdir()
    async with db.session() as session:
        lib = await LibraryRepository(session).create(name="Mixed", kind="mixed", root_paths=[str(root)])
        # Same numeric TMDB ID must remain separate movie/tv identities.
        for kind in ("movie", "tv"):
            session.add(MediaItem(kind=kind, tmdb_id=550, title="Fixture", original_title="Fixture", year=2020))
        await session.commit()
        rule = await ImportWatchConfigService(session).create(source_path=str(watch), strategy=strategy, library_id=lib.id)
    sources = []
    for kind in ("movie", "tv"):
        entry = watch / kind
        entry.mkdir()
        src = entry / ("Fixture.S01E01.mp4" if kind == "tv" else "Fixture.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=size=32x32:rate=1", "-t", "1", "-c:v", "mpeg4", str(src)], check=True)
        tag = "tvshow" if kind == "tv" else "movie"
        (entry / f"{tag}.nfo").write_text(f"<{tag}><title>Fixture</title><tmdbid>550</tmdbid></{tag}>")
        os.utime(src, (1, 1))
        sources.append(src)
    ambiguous = watch / "ambiguous"
    ambiguous.mkdir()
    (ambiguous / "unknown.mp4").write_bytes(sources[0].read_bytes())
    os.utime(ambiguous / "unknown.mp4", (1, 1))
    for _ in range(3):
        await ingest._sweep_dir(rule, lib, execute_inline=True)
    async with db.session() as session:
        files = list((await session.execute(select(LibraryFile))).scalars())
        records = list((await session.execute(select(IngestEntry))).scalars())
        items = {i.id: i for i in (await session.execute(select(MediaItem))).scalars()}
    assert len(files) == 2
    assert sorted(r.status for r in records) == sorted([IngestStatus.IMPORTED, IngestStatus.IMPORTED, IngestStatus.PENDING])
    for file in files:
        kind = items[file.media_item_id].kind
        target = __import__('pathlib').Path(file.file_path)
        source = sources[0 if kind == "movie" else 1]
        assert target.is_relative_to(root / kind)
        assert target.read_bytes() == source.read_bytes()
        assert (target.stat().st_ino == source.stat().st_ino) == (strategy == "hardlink")
        if kind == "tv":
            assert file.season_number == 1 and file.episode_number == 1
    await ingest._sweep_dir(rule, lib, execute_inline=True)
    async with db.session() as session:
        assert len(list((await session.execute(select(LibraryFile))).scalars())) == 2


@pytest.mark.asyncio
async def test_mixed_rules_are_candidates_not_defaults(db, tmp_path):
    async with db.session() as session:
        repo = LibraryRepository(session)
        defaults = {}
        for kind in ("movie", "tv"):
            defaults[kind] = await repo.create(name=kind, kind=kind, root_paths=[str(tmp_path / kind)])
        mixed = await repo.create(name="mixed", kind="mixed", root_paths=[str(tmp_path / 'mixed')])
        mixed.match_rules = [{"field": "origin_countries", "op": "any_of", "values": ["JP"]}]
        session.add(mixed)
        await session.commit()
        for kind in ("movie", "tv"):
            hit = await route(session, kind, RoutingFacts(origin_countries=("JP",)))
            assert hit.matched and hit.library.id == mixed.id
            miss = await route(session, kind, RoutingFacts(origin_countries=("US",)))
            assert not miss.matched and miss.library.id == defaults[kind].id
