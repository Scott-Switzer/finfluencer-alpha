from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .budget_guard import estimate_cost
from .config import get_settings
from .creator_taxonomy import seed_creator_taxonomy
from .db import connect, init_db


@dataclass(frozen=True)
class CreatorResearchMetrics:
    platform: str
    handle_or_channel: str
    initial_category: str = "unknown"
    count_stockpick_filtered: int = 0
    estimated_x_reads: int = 0
    ticker_density: float = 0.0
    actionable_density: float = 0.0
    engagement_available: bool = False
    cross_platform_present: bool = False


@dataclass(frozen=True)
class CreatorSelectionResult:
    creator_selection_score: float
    recommended_action: str
    reason: str


@dataclass(frozen=True)
class EnrichmentEventPlan:
    candidate_id: int
    source_id: str
    reply_read_cap: int
    quote_read_cap: int


def _category_originality(category: str) -> float:
    return {
        "stock_picker": 1.0,
        "meme_retail": 0.65,
        "analytical_control": 0.60,
        "macro_commentary": 0.35,
        "unknown": 0.35,
        "news_attention": 0.10,
    }.get(category, 0.35)


def _estimated_actionable_count(metrics: CreatorResearchMetrics) -> float:
    category_rate = {
        "stock_picker": 0.40,
        "meme_retail": 0.28,
        "analytical_control": 0.16,
        "macro_commentary": 0.08,
        "unknown": 0.10,
        "news_attention": 0.04,
    }.get(metrics.initial_category, 0.10)
    observed = metrics.actionable_density * metrics.count_stockpick_filtered
    prior = metrics.count_stockpick_filtered * category_rate
    return max(observed, prior)


def score_creator_for_research_sample(
    creator: CreatorResearchMetrics | dict[str, Any],
) -> CreatorSelectionResult:
    settings = get_settings()
    metrics = creator if isinstance(creator, CreatorResearchMetrics) else CreatorResearchMetrics(**creator)
    count = max(metrics.count_stockpick_filtered, 0)
    estimated_reads = max(metrics.estimated_x_reads, count if metrics.platform == "x" else 0)
    estimated_actionable = _estimated_actionable_count(metrics)
    actionable_density = (
        metrics.actionable_density if metrics.actionable_density else estimated_actionable / count if count else 0
    )
    cost_efficiency = (estimated_actionable / estimated_reads * 1000) if estimated_reads else 0

    count_component = min(count / max(settings.min_creator_stock_pick_count, 1), 2.0) * 18
    ticker_component = min(metrics.ticker_density, 1.0) * 15
    actionable_component = min(actionable_density, 0.60) / 0.60 * 22
    originality_component = _category_originality(metrics.initial_category) * 18
    engagement_component = 7 if metrics.engagement_available else 0
    cross_platform_component = 8 if metrics.cross_platform_present else 0
    efficiency_component = min(cost_efficiency / 80, 1.0) * 12
    score = round(
        count_component
        + ticker_component
        + actionable_component
        + originality_component
        + engagement_component
        + cross_platform_component
        + efficiency_component,
        3,
    )

    if metrics.initial_category == "news_attention":
        return CreatorSelectionResult(
            creator_selection_score=min(score, 49.0),
            recommended_action="exclude_too_news_heavy",
            reason="Seed taxonomy marks this account as news/attention; useful as context but not primary stock-picker sample.",
        )
    if metrics.initial_category == "analytical_control":
        return CreatorSelectionResult(
            creator_selection_score=score,
            recommended_action="include_control",
            reason="Analytical control account; include separately from stock-picking finfluencer sample.",
        )
    if metrics.initial_category == "macro_commentary":
        return CreatorSelectionResult(
            creator_selection_score=score,
            recommended_action="include_control" if count >= settings.min_creator_stock_pick_count else "needs_manual_review",
            reason="Macro/commentary account; screen as attention/control rather than primary stock-picker.",
        )
    if count < settings.min_creator_stock_pick_count:
        return CreatorSelectionResult(
            creator_selection_score=score,
            recommended_action="exclude_too_low_signal",
            reason=f"Only {count} stock-pick-filtered items; minimum is {settings.min_creator_stock_pick_count}.",
        )
    if estimated_actionable < settings.min_creator_actionable_count:
        return CreatorSelectionResult(
            creator_selection_score=score,
            recommended_action="needs_manual_review",
            reason=(
                f"Estimated actionable count is {estimated_actionable:.1f}; "
                f"target minimum is {settings.min_creator_actionable_count}."
            ),
        )
    if metrics.initial_category in {"stock_picker", "meme_retail"}:
        reason = (
            "YouTube stock-pick-oriented channel with enough historical metadata volume for review."
            if metrics.platform == "youtube"
            else "Stock-pick-oriented creator with enough filtered count to justify paid X retrieval."
        )
        return CreatorSelectionResult(
            creator_selection_score=score,
            recommended_action="include_primary",
            reason=reason,
        )
    return CreatorSelectionResult(
        creator_selection_score=score,
        recommended_action="needs_manual_review",
        reason="Creator has enough signal but taxonomy is unknown; manually screen before inclusion.",
    )


def _latest_x_count_by_handle(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT handle, total_tweet_count
        FROM x_query_counts c
        WHERE handle IS NOT NULL
          AND count_id = (
            SELECT MAX(count_id)
            FROM x_query_counts c2
            WHERE c2.handle = c.handle
          )
        """
    ).fetchall()
    return {row["handle"]: int(row["total_tweet_count"] or 0) for row in rows}


def _cross_platform_names(conn) -> set[str]:
    rows = conn.execute("SELECT platform, handle_or_channel FROM creator_taxonomy").fetchall()
    x_names = {row["handle_or_channel"].lower() for row in rows if row["platform"] == "x"}
    youtube_names = {row["handle_or_channel"].lower() for row in rows if row["platform"] == "youtube"}
    cross: set[str] = set()
    for name in x_names:
        compact = name.replace("real", "").replace("iam", "").replace(" ", "")
        if any(compact and compact in yt.replace(" ", "").lower() for yt in youtube_names):
            cross.add(name)
    return cross


def build_creator_selection(read_budget: int | None = None) -> list[dict[str, Any]]:
    init_db()
    seed_creator_taxonomy()
    settings = get_settings()
    read_budget = read_budget if read_budget is not None else settings.x_main_collection_read_budget
    rows_out: list[dict[str, Any]] = []

    with connect() as conn:
        counts = _latest_x_count_by_handle(conn)
        cross_names = _cross_platform_names(conn)
        taxonomy_rows = conn.execute(
            """
            SELECT platform, handle_or_channel, initial_category, notes
            FROM creator_taxonomy
            ORDER BY platform, handle_or_channel
            """
        ).fetchall()
        conn.execute("DELETE FROM creator_selection")
        for row in taxonomy_rows:
            platform = row["platform"]
            handle = row["handle_or_channel"]
            count = counts.get(handle, 0) if platform == "x" else 0
            if platform == "youtube":
                video_row = conn.execute(
                    """
                    SELECT COUNT(*) AS total_items
                    FROM raw_youtube_videos
                    WHERE channel_id = ? OR LOWER(channel_title) = LOWER(?)
                    """,
                    (handle, handle),
                ).fetchone()
                count = int(video_row["total_items"] or 0)
            estimated_reads = count if platform == "x" else 0
            ticker_row = conn.execute(
                """
                SELECT
                  COUNT(DISTINCT tm.mention_id) AS ticker_mentions,
                  COUNT(DISTINCT rc.candidate_id) AS actionable_mentions,
                  COUNT(DISTINCT COALESCE(x.post_id, y.video_id)) AS total_items
                FROM creators c
                LEFT JOIN raw_x_posts x
                  ON c.platform = 'x' AND c.handle = x.creator_handle
                LEFT JOIN raw_youtube_videos y
                  ON c.platform = 'youtube'
                  AND (c.handle = y.channel_id OR LOWER(c.display_name) = LOWER(y.channel_title))
                LEFT JOIN ticker_mentions tm
                  ON tm.platform = c.platform
                  AND tm.source_id = COALESCE(x.post_id, y.video_id)
                LEFT JOIN recommendation_candidates rc
                  ON rc.platform = c.platform
                  AND rc.source_id = COALESCE(x.post_id, y.video_id)
                WHERE c.platform = ? AND c.handle = ?
                """,
                (platform, handle),
            ).fetchone()
            total_items = int(ticker_row["total_items"] or count or 0)
            ticker_mentions = int(ticker_row["ticker_mentions"] or 0)
            actionable_mentions = int(ticker_row["actionable_mentions"] or 0)
            ticker_density = ticker_mentions / total_items if total_items else 0.0
            actionable_density = actionable_mentions / total_items if total_items else 0.0
            metrics = CreatorResearchMetrics(
                platform=platform,
                handle_or_channel=handle,
                initial_category=row["initial_category"],
                count_stockpick_filtered=count,
                estimated_x_reads=estimated_reads,
                ticker_density=ticker_density,
                actionable_density=actionable_density,
                engagement_available=total_items > 0,
                cross_platform_present=handle.lower() in cross_names,
            )
            result = score_creator_for_research_sample(metrics)
            rows_out.append(
                {
                    "platform": platform,
                    "handle_or_channel": handle,
                    "initial_category": row["initial_category"],
                    "count_stockpick_filtered": count,
                    "estimated_x_reads": estimated_reads,
                    "estimated_x_cost": estimate_cost(estimated_reads),
                    "ticker_density": round(ticker_density, 4),
                    "actionable_density": round(actionable_density, 4),
                    "creator_selection_score": result.creator_selection_score,
                    "recommended_action": result.recommended_action,
                    "reason": result.reason,
                    "selected_for_collection": 0,
                }
            )

        remaining_reads = max(read_budget, 0)
        for row in sorted(
            rows_out,
            key=lambda item: (
                item["recommended_action"] == "include_primary",
                item["creator_selection_score"],
            ),
            reverse=True,
        ):
            if row["platform"] != "x" or row["recommended_action"] != "include_primary":
                continue
            reads = int(row["estimated_x_reads"] or 0)
            if reads <= remaining_reads:
                row["selected_for_collection"] = 1
                remaining_reads -= reads

        for row in rows_out:
            conn.execute(
                """
                INSERT INTO creator_selection (
                  platform, handle_or_channel, initial_category,
                  count_stockpick_filtered, estimated_x_reads, estimated_x_cost,
                  ticker_density, actionable_density, creator_selection_score,
                  recommended_action, reason, selected_for_collection
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, handle_or_channel) DO UPDATE SET
                  initial_category = excluded.initial_category,
                  count_stockpick_filtered = excluded.count_stockpick_filtered,
                  estimated_x_reads = excluded.estimated_x_reads,
                  estimated_x_cost = excluded.estimated_x_cost,
                  ticker_density = excluded.ticker_density,
                  actionable_density = excluded.actionable_density,
                  creator_selection_score = excluded.creator_selection_score,
                  recommended_action = excluded.recommended_action,
                  reason = excluded.reason,
                  selected_for_collection = excluded.selected_for_collection
                """,
                (
                    row["platform"],
                    row["handle_or_channel"],
                    row["initial_category"],
                    row["count_stockpick_filtered"],
                    row["estimated_x_reads"],
                    row["estimated_x_cost"],
                    row["ticker_density"],
                    row["actionable_density"],
                    row["creator_selection_score"],
                    row["recommended_action"],
                    row["reason"],
                    row["selected_for_collection"],
                ),
            )
        conn.commit()
    return rows_out


def plan_enrichment_events(
    candidates: list[dict[str, Any]],
    max_events: int,
    max_replies: int,
    max_quotes: int,
    remaining_reads: int,
) -> list[EnrichmentEventPlan]:
    plans: list[EnrichmentEventPlan] = []
    for candidate in candidates[: max(max_events, 0)]:
        if remaining_reads <= 0:
            break
        reply_cap = min(max_replies, remaining_reads)
        remaining_reads -= reply_cap
        quote_cap = min(max_quotes, remaining_reads)
        remaining_reads -= quote_cap
        if reply_cap + quote_cap <= 0:
            break
        plans.append(
            EnrichmentEventPlan(
                candidate_id=int(candidate["candidate_id"]),
                source_id=str(candidate["source_id"]),
                reply_read_cap=reply_cap,
                quote_read_cap=quote_cap,
            )
        )
    return plans
