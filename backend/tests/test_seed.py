"""Phase 3.4 seed-script tests.

The seed script is the integration point for the whole ingestion
stack — client, normalizer, loader, quota. Tests have to verify the
quota-aware behavior the user demanded:

  * Worst-case calls are computed before any network IO.
  * Strict mode aborts (no DB writes) if projected > remaining.
  * --partial mode runs until the quota actually exhausts.
  * Whatever does get loaded survives a re-run unchanged
    (idempotency, inherited from Phase 3.3).

All CricAPI traffic is mocked via httpx.MockTransport so the tests
don't burn quota or depend on the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.models import BattingStats, BowlingStats, Match, Player
from ingestion.client import CricAPIClient
from ingestion.seed import (
    PLAYER_SEED_LIST,
    TARGET_MIX,
    pick_matches,
    run_seed,
)
from app.models.enums import MatchType

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _build_handler(
    *,
    players_response: Callable[[str], dict] | None = None,
    player_stats_response: Callable[[str], dict] | None = None,
    match_response: Callable[[str], dict] | None = None,
):
    """Construct a httpx.MockTransport handler that routes the three
    endpoints we care about to the supplied callables."""

    def handler(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.split("/")[-1]
        params = dict(request.url.params)
        if endpoint == "players" and players_response:
            return httpx.Response(200, json=players_response(params.get("search", "")))
        if endpoint == "playerStats" and player_stats_response:
            return httpx.Response(200, json=player_stats_response(params.get("id", "")))
        if endpoint == "match" and match_response:
            return httpx.Response(200, json=match_response(params.get("id", "")))
        # Default: empty success
        return httpx.Response(200, json={"status": "success", "data": []})

    return handler


def _wrap_factory_for_session(session):
    """Return a 'session_factory' that yields the *same* db_session
    fixture across the seed run, instead of opening a new connection.

    The seed's _finalise expects a context-manager factory (with the
    pattern `with factory() as session`). We wrap our existing
    pytest fixture-managed session so commit() inside the seed
    persists rows the test can then assert on.
    """

    class _Factory:
        def __call__(self):
            return self

        def __enter__(self_inner):
            return session

        def __exit__(self_inner, *exc):
            return False

    return _Factory()


# ====================================================================
# Pre-flight & plan-only behavior
# ====================================================================

class TestPreflight:

    def test_strict_mode_aborts_when_projected_exceeds_quota(self, db_session, tmp_path):
        # Empty cache means worst-case = full plan. With the default
        # daily quota of 100 and a 22-player plan needing 144 calls,
        # the strict path must abort and write nothing to the DB.
        transport = httpx.MockTransport(_build_handler())
        client_factory_called = {"n": 0}

        def make_client(*args, **kwargs):
            client_factory_called["n"] += 1
            return CricAPIClient(
                api_key="test-key",
                base_url="https://api.cricapi.com/v1",
                cache_root=tmp_path,
                http_client=httpx.Client(transport=transport),
            )

        # Monkey-patch the seed to use our mocked client.
        import ingestion.seed as seed_mod
        original = seed_mod.CricAPIClient
        seed_mod.CricAPIClient = make_client
        try:
            report = run_seed(
                partial=False,
                api_key="test-key",
                db_session_factory=_wrap_factory_for_session(db_session),
            )
        finally:
            seed_mod.CricAPIClient = original

        assert report.aborted_pre_flight is True
        # Crucially, NO DB writes happened — the abort short-circuits
        # before any phase begins.
        assert db_session.scalar(__import__("sqlalchemy").select(__import__("sqlalchemy").func.count()).select_from(Player)) == 0

    def test_plan_only_makes_no_calls_and_no_writes(self, db_session, tmp_path):
        transport = httpx.MockTransport(_build_handler())

        import ingestion.seed as seed_mod
        original = seed_mod.CricAPIClient
        seed_mod.CricAPIClient = lambda *a, **kw: CricAPIClient(
            api_key="test-key",
            cache_root=tmp_path,
            http_client=httpx.Client(transport=transport),
        )
        try:
            report = run_seed(
                plan_only=True,
                api_key="test-key",
                db_session_factory=_wrap_factory_for_session(db_session),
            )
        finally:
            seed_mod.CricAPIClient = original

        # plan_only doesn't even attempt DB writes; just reports.
        from sqlalchemy import select, func
        assert db_session.scalar(select(func.count()).select_from(Player)) == 0
        assert report.worst_case_calls > 0


# ====================================================================
# Match-pick logic (pure, no client)
# ====================================================================

class TestPickMatches:

    def test_picks_per_format_quota(self):
        # Build a pool with way more than the target of each format
        pool = (
            [(f"t20i-{i}", MatchType.T20I) for i in range(50)]
            + [(f"odi-{i}", MatchType.ODI) for i in range(50)]
            + [(f"test-{i}", MatchType.TEST) for i in range(50)]
            + [(f"t20-{i}", MatchType.T20) for i in range(50)]
        )
        picked = pick_matches(pool, TARGET_MIX)
        from collections import Counter
        # Verify exact mix matches the target (30/30/25/15).
        prefixes = Counter(p.split("-")[0] for p in picked)
        assert prefixes["t20i"] == 30
        assert prefixes["odi"] == 30
        assert prefixes["test"] == 25
        assert prefixes["t20"] == 15
        assert len(picked) == 100

    def test_unknown_format_fills_shortfall(self):
        # Only 10 T20s are available; the remaining 5 should come from
        # the unknown bucket since T20 is the leftover-fill target.
        pool = (
            [(f"t20i-{i}", MatchType.T20I) for i in range(30)]
            + [(f"odi-{i}", MatchType.ODI) for i in range(30)]
            + [(f"test-{i}", MatchType.TEST) for i in range(25)]
            + [(f"t20-{i}", MatchType.T20) for i in range(10)]
            + [(f"x-{i}", None) for i in range(20)]
        )
        picked = pick_matches(pool, TARGET_MIX)
        assert len(picked) == 100
        unknown_used = sum(1 for p in picked if p.startswith("x-"))
        assert unknown_used == 5  # 15 target − 10 known T20s


# ====================================================================
# End-to-end with mocked CricAPI + small target
# ====================================================================

class TestFullSeedRun:
    """Drive the full seed pipeline against a mocked CricAPI. Use a
    tiny target so the projected call count stays under quota and we
    actually exercise the player → stats → match → load path."""

    @pytest.fixture
    def tiny_seed(self, monkeypatch, db_session, tmp_path):
        # 2 players × 1 stats lookup × 2 matches = 6 calls — well
        # under the default 100/day quota.
        monkeypatch.setattr(
            "ingestion.seed.PLAYER_SEED_LIST", ["Babar Azam", "Virat Kohli"]
        )

        # Mocked CricAPI:
        #   /players?search=<name> → returns one player with id `p-<name>`
        #   /playerStats?id=p-<name> → matchList with 2 entries
        #   /match?id=<match> → reuses our normalizer fixture
        clean = _load_fixture("match_clean_t20i.json")

        def players_response(search: str) -> dict:
            slug = "babar-azam" if "Babar" in search else "virat-kohli"
            return {
                "status": "success",
                "data": [
                    {
                        "id": f"p-{slug}",
                        "name": search,
                        "country": "Pakistan" if "Babar" in search else "India",
                    }
                ],
            }

        def stats_response(player_id: str) -> dict:
            return {
                "status": "success",
                "data": {
                    "matchList": [
                        {"matchId": "m-001", "matchType": "t20i"},
                        {"matchId": "m-002", "matchType": "t20i"},
                    ]
                },
            }

        def match_response(match_id: str) -> dict:
            # Re-use the clean T20I fixture but override ids so each
            # match_id maps to a distinct external_id in the DB.
            payload = dict(clean)
            payload["id"] = match_id
            return {"status": "success", "data": payload}

        transport = httpx.MockTransport(
            _build_handler(
                players_response=players_response,
                player_stats_response=stats_response,
                match_response=match_response,
            )
        )

        def factory(*args, **kwargs):
            return CricAPIClient(
                api_key="test-key",
                base_url="https://api.cricapi.com/v1",
                cache_root=tmp_path,
                http_client=httpx.Client(transport=transport),
            )

        monkeypatch.setattr("ingestion.seed.CricAPIClient", factory)
        return {"db_session": db_session}

    def test_seed_loads_players_and_matches(self, tiny_seed):
        report = run_seed(
            target_matches=2,
            target_mix={MatchType.T20I: 2},
            api_key="test-key",
            db_session_factory=_wrap_factory_for_session(tiny_seed["db_session"]),
        )

        from sqlalchemy import func, select
        s = tiny_seed["db_session"]
        assert s.scalar(select(func.count()).select_from(Match)) == 2
        assert s.scalar(select(func.count()).select_from(Player)) >= 2
        assert s.scalar(select(func.count()).select_from(BattingStats)) > 0
        assert s.scalar(select(func.count()).select_from(BowlingStats)) > 0
        assert report.matches_loaded == 2
        assert report.players_resolved == 2

    def test_seed_is_idempotent(self, tiny_seed):
        # Run twice — second run must NOT inflate row counts.
        from sqlalchemy import func, select

        run_seed(
            target_matches=2,
            target_mix={MatchType.T20I: 2},
            api_key="test-key",
            db_session_factory=_wrap_factory_for_session(tiny_seed["db_session"]),
        )
        s = tiny_seed["db_session"]
        first = {
            "players": s.scalar(select(func.count()).select_from(Player)),
            "matches": s.scalar(select(func.count()).select_from(Match)),
            "batting": s.scalar(select(func.count()).select_from(BattingStats)),
            "bowling": s.scalar(select(func.count()).select_from(BowlingStats)),
        }

        run_seed(
            target_matches=2,
            target_mix={MatchType.T20I: 2},
            api_key="test-key",
            db_session_factory=_wrap_factory_for_session(tiny_seed["db_session"]),
        )
        second = {
            "players": s.scalar(select(func.count()).select_from(Player)),
            "matches": s.scalar(select(func.count()).select_from(Match)),
            "batting": s.scalar(select(func.count()).select_from(BattingStats)),
            "bowling": s.scalar(select(func.count()).select_from(BowlingStats)),
        }
        assert first == second, (
            f"seed not idempotent: first={first}, second={second}"
        )

    def test_partial_mode_handles_quota_exhaustion(self, monkeypatch, db_session, tmp_path):
        # Drive a tiny quota so we hit RateLimitError mid-run.
        # 2 players × 2 calls (search+stats) = 4 — set quota at 3.
        monkeypatch.setattr(
            "ingestion.seed.PLAYER_SEED_LIST", ["Babar Azam", "Virat Kohli"]
        )

        def players_response(search: str) -> dict:
            slug = "babar-azam" if "Babar" in search else "virat-kohli"
            return {"status": "success", "data": [{"id": f"p-{slug}", "name": search, "country": "Pakistan"}]}

        def stats_response(player_id: str) -> dict:
            return {"status": "success", "data": {"matchList": []}}

        transport = httpx.MockTransport(
            _build_handler(
                players_response=players_response,
                player_stats_response=stats_response,
            )
        )

        def factory(*args, **kwargs):
            return CricAPIClient(
                api_key="test-key",
                cache_root=tmp_path,
                daily_limit=3,
                http_client=httpx.Client(transport=transport),
            )

        monkeypatch.setattr("ingestion.seed.CricAPIClient", factory)

        report = run_seed(
            partial=True,
            target_matches=0,
            target_mix={MatchType.T20I: 0},
            api_key="test-key",
            db_session_factory=_wrap_factory_for_session(db_session),
        )

        # We should have hit the rate limit somewhere mid-run, and
        # whatever players resolved before the wall remain in the DB.
        assert report.rate_limit_hit is True
        from sqlalchemy import func, select
        # At least one player resolved before quota exhausted.
        assert db_session.scalar(select(func.count()).select_from(Player)) >= 1


# ====================================================================
# Sanity on the configured roster
# ====================================================================

def test_player_seed_list_has_expected_count_and_pakistan_first():
    # The seed list must have all 22 players the user specified.
    assert len(PLAYER_SEED_LIST) == 22
    # Pakistan core comes first so the dashboard's default "highlighted"
    # player on the comparison page is a Pakistan player.
    assert PLAYER_SEED_LIST[0] == "Babar Azam"


def test_target_mix_sums_to_100():
    assert sum(TARGET_MIX.values()) == 100
