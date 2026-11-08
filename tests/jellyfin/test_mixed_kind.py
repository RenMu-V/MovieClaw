"""Mixed library protocol regression using real SQLite and HTTP DTOs."""

import asyncio

import pytest
from sqlmodel import select

from jellyfin.helpers import jf_login
from movieclaw_api.core.config import get_settings
from movieclaw_db.engine import dispose_db, get_database, init_db
from movieclaw_db.models import Library, LibraryFile
from movieclaw_jellyfin.ids import library_guid


@pytest.fixture
def mixed_seed(seeded):
    async def merge():
        init_db(get_settings().database_url, echo=False)
        async with get_database().session() as session:
            lib = await session.get(Library, seeded["movie_lib"])
            assert lib is not None and lib.id is not None
            lib.kind = "mixed"
            session.add(lib)
            rows = (
                (
                    await session.execute(
                        select(LibraryFile).where(LibraryFile.library_id == seeded["tv_lib"])
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                row.library_id = lib.id
                session.add(row)
            await session.commit()
        await dispose_db()

    asyncio.run(merge())
    return seeded


def test_mixed_collection_movies_series_seasons_episodes(mixed_seed, client):
    token = jf_login(client)
    headers = {"X-Emby-Token": token, "User-Agent": "Yamby/2.1.0.11(Android"}
    lid = library_guid(mixed_seed["movie_lib"])
    library = client.get(f"/Items/{lid}", headers=headers)
    assert library.status_code == 200, library.text
    assert library.json().get("CollectionType", "") == ""
    items = client.get("/Items", params={"ParentId": lid, "Recursive": "false"}, headers=headers)
    assert items.status_code == 200, items.text
    assert {x["Type"] for x in items.json()["Items"]} == {"Movie", "Series"}
    show = next(x for x in items.json()["Items"] if x["Type"] == "Series")
    seasons = client.get(f"/Shows/{show['Id']}/Seasons", headers=headers)
    assert seasons.status_code == 200, seasons.text
    assert {x["IndexNumber"] for x in seasons.json()["Items"]} == {1, 2}
    episodes = client.get(f"/Shows/{show['Id']}/Episodes", headers=headers)
    assert episodes.status_code == 200, episodes.text
    assert {(x["ParentIndexNumber"], x["IndexNumber"]) for x in episodes.json()["Items"]} == {
        (1, 1),
        (1, 2),
        (2, 1),
    }
