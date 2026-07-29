"""Human-readable job outcomes so MCP clients can choose next steps.

Local-first messaging: coverage facts, not broker-passthrough alarms.
No secrets or account balances — only counts, reasons, and actions.
"""

from __future__ import annotations

from typing import Any


def enrich_job_payload(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Attach message / next_steps / client_guidance to a job or pipeline result."""
    out = dict(payload)
    result = out.get("result") if isinstance(out.get("result"), dict) else out
    reason = out.get("reason") or (result or {}).get("reason")
    state = out.get("state")
    ok = out.get("ok")
    skipped = out.get("skipped")

    if job_id in ("connector_sync", "sync"):
        msg, steps, guide = _connector_sync_guidance(result or out, ok, skipped, reason)
    elif job_id == "daily_net_liq":
        msg, steps, guide = _net_liq_guidance(result or out, ok, skipped, reason)
    elif job_id in ("data_refresh", "refresh"):
        if skipped and reason == "already_running":
            msg = (
                "Data refresh already in progress (hourly or another client). "
                "No duplicate sync/recalc was started."
            )
            steps = [
                "Poll jobs_status_tool(job_id='data_refresh') until finished.",
                "Then serve answers from local equity snapshots and daily_account_net_liq.",
            ]
            guide = {
                "outcome": "already_running",
                "action": "wait_then_serve_local",
                "local_first": True,
            }
        else:
            msg, steps, guide = _pipeline_guidance(out, ok, reason)
    else:
        msg = f"Job {job_id} finished with state={state} reason={reason}."
        steps = [
            "Call jobs_status_tool for details.",
            "Call jobs_list_tool for catalog.",
        ]
        guide = {"outcome": state or reason}

    out["message"] = msg
    out["next_steps"] = steps
    out["client_guidance"] = guide
    if isinstance(out.get("result"), dict):
        out["result"] = {
            **out["result"],
            "message": out["result"].get("message") or msg,
            "next_steps": out["result"].get("next_steps") or steps,
            "client_guidance": out["result"].get("client_guidance") or guide,
        }
    return out


def _connector_sync_guidance(
    result: dict[str, Any],
    ok: Any,
    skipped: Any,
    reason: Any,
) -> tuple[str, list[str], dict[str, Any]]:
    brokers = result.get("brokers") or []
    n_ok = sum(1 for b in brokers if b.get("ok"))
    n_fail = sum(1 for b in brokers if not b.get("ok") and not b.get("skipped"))
    n_acct = sum(int(b.get("accounts") or 0) for b in brokers)
    n_snap = sum(int(b.get("snapshots") or 0) for b in brokers)
    n_pos = sum(int(b.get("positions") or 0) for b in brokers)
    errors = [
        f"{b.get('broker')}: {b.get('error') or b.get('reason')}"
        for b in brokers
        if b.get("error") or (not b.get("ok") and not b.get("skipped"))
    ]

    if skipped and reason == "already_running":
        return (
            "Connector sync skipped: another sync holds the lock.",
            [
                "Wait, then jobs_status_tool(job_id='connector_sync') or data_refresh.",
                "Serve from existing local GT if present.",
            ],
            {"outcome": "already_running", "local_first": True},
        )
    if skipped and reason == "not_stale":
        return (
            "Connector sync skipped: local cache still fresh (min-interval).",
            [
                "Use force=true to pull remote again, or run data_refresh to re-derive NLV.",
                "Serve current answers from local GT.",
            ],
            {"outcome": "not_stale", "local_first": True},
        )
    if ok and n_fail == 0:
        msg = (
            f"Local GT cache updated: {n_ok} broker(s), {n_acct} account(s), "
            f"{n_snap} equity row(s), {n_pos} position row(s). "
            "Remote was used only to enrich the cache—not as a query passthrough."
        )
        steps = [
            "Run refresh_portfolio_data_tool or jobs_run_tool(job_id='daily_net_liq') "
            "to maximize local daily NLV from raw (if not already in data_refresh).",
            "Serve current NLV from latest local equity snapshot.",
        ]
        return (
            msg,
            steps,
            {
                "outcome": "sync_ok",
                "accounts": n_acct,
                "snapshots": n_snap,
                "positions": n_pos,
                "local_first": True,
            },
        )
    if n_ok and n_fail:
        return (
            f"Partial local cache update: {n_ok} broker(s) ok, {n_fail} failed. "
            f"{'; '.join(errors) or ''}",
            [
                "Use accounts that synced; retry failed brokers via test_connector_tool.",
                "Still run NLV derive on local raw for successful accounts.",
            ],
            {"outcome": "partial_failure", "errors": errors, "local_first": True},
        )
    return (
        f"Remote→local sync failed (reason={reason}). "
        f"{'; '.join(errors) or 'No new raw written.'}",
        [
            "test_connector_tool / schwab-mcp / OAuth; retry data_refresh.",
            "Serve last local cache if available.",
        ],
        {"outcome": "sync_failed", "errors": errors, "local_first": True},
    )


def _net_liq_guidance(
    result: dict[str, Any],
    ok: Any,
    skipped: Any,
    reason: Any,
) -> tuple[str, list[str], dict[str, Any]]:
    cov = result.get("coverage") or {}
    req = cov.get("min_days_requested")
    min_series = cov.get("min_series_len")
    max_series = cov.get("max_series_len")
    n_gt = cov.get("rows_ground_truth")
    n_recon = cov.get("rows_reconstructed")
    skipped_src = cov.get("rows_skipped_no_source")
    window = f"{cov.get('window_start')}…{cov.get('window_end')}"

    if skipped and reason == "already_running":
        return (
            "daily_net_liq skipped: job already running.",
            [
                "Poll jobs_status_tool(job_id='daily_net_liq'); serve local series when ready."
            ],
            {"outcome": "already_running", "local_first": True},
        )

    if reason in ("insufficient_history", "partial_coverage"):
        msg = (
            f"Local daily NLV derived (window {window}; "
            f"GT={n_gt}, reconstructed={n_recon}, no_source={skipped_src}). "
            f"Series length min={min_series} max={max_series}"
            + (f" vs requested min_days={req}" if req else "")
            + ". Sparse anchors + current snapshot is the correct product answer — "
            "not a missing-export failure. Live broker APIs do not return a multi-day "
            "NLV history; do not invent dense daily NLV."
        )
        steps = [
            "Answer CURRENT NLV from latest local equity / daily_account_net_liq row.",
            "Chart ONLY available local NLV anchors (get_account_nlv_series_tool → "
            "series / series_all_local). Sparse is OK.",
            "Do NOT ask the user to re-upload Schwab exports to 'unlock' a dense "
            "60-day NLV series — monthly statements and Positions CSVs do not create "
            "dense daily account NLV; re-upload only helps if they have NEW dated files.",
            "Do not treat short/sparse history as a hard service failure.",
        ]
        return (
            msg,
            steps,
            {
                "outcome": reason,
                "min_days_requested": req,
                "min_series_len": min_series,
                "max_series_len": max_series,
                "rows_ground_truth": n_gt,
                "rows_reconstructed": n_recon,
                "can_answer_current_snapshot": True,
                "serve_best_available_series": True,
                "chart_sparse_ok": True,
                "do_not_invent_missing_days": True,
                "do_not_recommend_export_upload_for_dense_nlv": True,
                "local_first": True,
            },
        )

    if ok and reason == "completed":
        msg = (
            f"Local NLV derive completed for {window}: "
            f"min_series={min_series} max={max_series} "
            f"(GT={n_gt}, reconstructed={n_recon}). "
            "provenance_days lists ground_truth / live_exact / reconstructed."
        )
        steps = [
            "Serve series from daily_account_net_liq.",
            "Current NLV from latest local snapshot or latest net-liq row.",
        ]
        return (
            msg,
            steps,
            {
                "outcome": "netliq_ok",
                "min_series_len": min_series,
                "max_series_len": max_series,
                "rows_ground_truth": n_gt,
                "rows_reconstructed": n_recon,
                "local_first": True,
                "can_answer_current_snapshot": True,
                "serve_best_available_series": True,
            },
        )

    return (
        f"Net-liq job ended reason={reason} ok={ok}.",
        [
            "Read result.coverage and accounts.",
            "refresh_portfolio_data_tool(force=true) for full local-first pipeline.",
        ],
        {"outcome": str(reason), "ok": ok, "local_first": True},
    )


def _pipeline_guidance(
    out: dict[str, Any],
    ok: Any,
    reason: Any,
) -> tuple[str, list[str], dict[str, Any]]:
    sync = out.get("connector_sync") or {}
    net = out.get("daily_net_liq") or {}
    sync_ok = sync.get("ok")
    net_reason = net.get("reason") or (net.get("result") or {}).get("reason")
    cov = (net.get("result") or net).get("coverage") or net.get("coverage") or {}

    if not sync_ok and not sync.get("skipped"):
        return (
            "Remote→local sync step failed; NLV derive used only existing local raw. "
            "Existing local cache can still be served if present.",
            [
                "Check connectors / schwab-mcp / OAuth; retry refresh_portfolio_data_tool(force=true).",
                "Answer from last local snapshots when available.",
            ],
            {
                "outcome": "pipeline_sync_failed",
                "sync": sync.get("reason"),
                "local_first": True,
                "can_serve_stale_local": True,
            },
        )

    if net_reason in ("insufficient_history", "partial_coverage") or reason in (
        "insufficient_history",
        "partial_coverage",
    ):
        msg = (
            "Local-first refresh finished: remote merged into local GT, export equity "
            "seeded when present, NLV maximized from real local anchors "
            f"(min_series_len={cov.get('min_series_len')}, "
            f"GT={cov.get('rows_ground_truth')}, recon={cov.get('rows_reconstructed')}). "
            "Serve CURRENT NLV + sparse best-available series from local DB. "
            "Dense multi-day NLV is not a broker API product; do not invent it."
        )
        steps = [
            "Report current account NLV from latest local equity / net-liq row.",
            "For history charts use get_account_nlv_series_tool (series + series_all_local).",
            "Do NOT prompt for Schwab export re-upload as the fix for dense 60-day NLV.",
            "Short/sparse history is expected coverage, not a portfolio-analysis failure.",
        ]
        return (
            msg,
            steps,
            {
                "outcome": "pipeline_ok_best_available",
                "min_series_len": cov.get("min_series_len"),
                "min_days_requested": cov.get("min_days_requested"),
                "can_answer_current_snapshot": True,
                "serve_best_available_series": True,
                "chart_sparse_ok": True,
                "do_not_invent_missing_days": True,
                "do_not_recommend_export_upload_for_dense_nlv": True,
                "local_first": True,
            },
        )

    if ok:
        return (
            "Local-first refresh completed: local GT cache updated, daily NLV derived from local raw.",
            [
                "Serve analysis from local snapshots + daily_account_net_liq.",
                "Use provenance_days to separate broker snapshots vs reconstructed days.",
            ],
            {
                "outcome": "pipeline_ok",
                "net_liq_reason": net_reason,
                "local_first": True,
                "can_answer_current_snapshot": True,
                "serve_best_available_series": True,
            },
        )

    return (
        f"Data refresh finished with issues (reason={reason}).",
        [
            "Inspect connector_sync and daily_net_liq sections.",
            "Serve last known local data if present; retry refresh later.",
        ],
        {"outcome": "pipeline_issues", "reason": reason, "local_first": True},
    )
