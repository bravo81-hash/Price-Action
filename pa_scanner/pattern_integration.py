"""Rank Price-Action signals with Forward-Vol-Scanner chart patterns.

The primary scanner remains authoritative for its S1-S4 evidence model.  This
adapter runs only the tickers that already survived that scan through the
current Forward-Vol-Scanner pattern engine, then promotes actionable pattern
matches for visual review.  A pattern match is an ordering aid, not a new trade
signal or a reason to increase size.
"""
from __future__ import annotations

from collections import defaultdict

from .fvs_patterns import SOURCE_COMMIT, SOURCE_REPOSITORY
from .fvs_patterns.scanner import SECTOR_ETFS, scan_patterns


def _compatible(base_side: str | None, pattern_side: str | None) -> bool | None:
    if base_side not in {"long", "short"}:
        return None
    return base_side == pattern_side


def _priority(base_side: str | None, pattern_side: str | None) -> int:
    aligned = _compatible(base_side, pattern_side)
    if aligned is True:
        return 0
    if aligned is None:
        return 1
    return 2


def _best_match(matches: list[dict], base_side: str | None) -> dict:
    return min(matches, key=lambda item: (
        _priority(base_side, item.get("side")),
        -float(item.get("score") or 0),
    ))


def annotate_pattern_matches(rows: list[dict], bundle: dict,
                             bench_daily=None) -> dict:
    """Annotate and reorder scan rows using actionable FVS pattern matches.

    ``bundle`` uses the existing Price-Action ``{ticker: (daily, weekly)}``
    shape, so no second market-data download is required.
    """
    tickers = list(dict.fromkeys(str(row.get("ticker") or "").upper()
                                for row in rows if row.get("ticker")))
    daily = {ticker: bundle[ticker] for ticker in tickers if ticker in bundle}
    sectors = {ticker: bundle[ticker][0] for ticker in SECTOR_ETFS
               if ticker in bundle}
    if not daily:
        for row in rows:
            row.update(pattern_match=False, pattern_priority=3)
        return {
            "source": SOURCE_REPOSITORY, "source_commit": SOURCE_COMMIT,
            "tickers_scanned": 0, "matched_tickers": 0,
            "matched_rows": 0, "status": "ok",
        }

    # The FVS defaults retain only ten final candidates because that screen
    # starts with the whole market.  Here the input is already a shortlist, so
    # retain every actionable match and choose the best match per displayed row.
    capacity = max(100, len(daily) * 12)
    result = scan_patterns(
        daily,
        bench_daily=bench_daily,
        sector_daily=sectors,
        geometry_limit=capacity,
        context_limit=capacity,
        final_limit=capacity,
        include_forming=False,
    )
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for match in result.rows:
        by_ticker[str(match.get("ticker") or "").upper()].append(match)
    for matches in by_ticker.values():
        matches.sort(key=lambda item: float(item.get("score") or 0), reverse=True)

    matched_rows = 0
    for row in rows:
        matches = by_ticker.get(str(row.get("ticker") or "").upper(), [])
        if not matches:
            row.update(pattern_match=False, pattern_priority=3,
                       pattern_count=0)
            continue
        match = _best_match(matches, row.get("side"))
        alignment = _compatible(row.get("side"), match.get("side"))
        row.update({
            "pattern_match": True,
            "pattern_priority": _priority(row.get("side"), match.get("side")),
            "pattern_alignment": ("aligned" if alignment is True else
                                  "conflict" if alignment is False else "context"),
            "pattern_count": len(matches),
            "pattern_code": match.get("code"),
            "pattern_name": match.get("pattern"),
            "pattern_status": match.get("status"),
            "pattern_side": match.get("side"),
            "pattern_score": match.get("score"),
            "pattern_geometry_score": match.get("geometry_score"),
            "pattern_trigger": match.get("trigger"),
            "pattern_invalidation": match.get("invalidation"),
            "pattern_target": match.get("preferred_target", match.get("target")),
            "pattern_trade_location": match.get("trade_location"),
            "pattern_room_rr": match.get("room_rr"),
            "pattern_points": match.get("points") or {},
            "pattern_chart": match.get("chart") or {},
            "pattern_review": match.get("review_reason"),
        })
        matched_rows += 1

    rows.sort(key=lambda row: (
        int(row.get("pattern_priority", 3)),
        int(row.get("evidence_rank", 99)),
        -float(row.get("rank") or 0),
        -float(row.get("score") or 0),
    ))
    return {
        "source": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "tickers_scanned": len(daily),
        "geometry_count": result.geometry_count,
        "actionable_count": result.actionable_count,
        "matched_tickers": len(by_ticker),
        "matched_rows": matched_rows,
        "status": "ok",
        "meaning": "ordering_and_visual_review_only",
    }
