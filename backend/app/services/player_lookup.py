"""Player lookup helpers used by routers."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Player


async def get_player_by_id(session: AsyncSession, player_id: int) -> Player | None:
    return await session.get(Player, player_id)


async def list_players(
    session: AsyncSession,
    *,
    name: str | None = None,
    country: str | None = None,
    countries: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Player], int]:
    """Returns (rows, total_count) so the router can emit a paginated
    response. Total is computed before slicing for honest counts.

    `countries` is an optional whitelist (SQL `IN (…)`) used by the
    router's `test_nations_only` flag to scope results to international
    rosters — separate from `country` (an exact-match single value)
    so both can co-exist if a caller ever needs to combine them.
    """
    from sqlalchemy import func

    base_filters = []
    if name:
        # Case-insensitive partial match — friendly to dashboard search.
        base_filters.append(Player.name.ilike(f"%{name}%"))
    if country:
        base_filters.append(Player.country == country)
    if countries:
        base_filters.append(Player.country.in_(countries))

    count_stmt = select(func.count(Player.id))
    list_stmt = select(Player).order_by(Player.name)
    for f in base_filters:
        count_stmt = count_stmt.where(f)
        list_stmt = list_stmt.where(f)

    total = await session.scalar(count_stmt) or 0
    rows = (
        (await session.execute(list_stmt.limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return list(rows), int(total)
