"""API jurnali (§10): JSONL sxemasi, 30 kunlik saqlash, Markdown xulosa."""

import json
from datetime import UTC, datetime, timedelta

from backend.app.core import config
from backend.app.usage.tracker import (
    RECORD_FIELDS,
    build_usage_summary,
    purge_old_logs,
    read_run_calls,
    record_api_call,
)


async def test_jsonl_schema_exact_fields():
    rec = await record_api_call(
        run_id=5, service="gee_primary", operation="computePixels", purpose="sentinel2_download",
        dataset="COPERNICUS/S2_SR_HARMONIZED", request="tile", status="success", duration_ms=12.345,
        bytes_count=1024, retries=1, failover=False, tokens_in=None, error=None,
    )
    files = list(config.API_CALLS_LOG_DIR.glob("*.jsonl"))
    assert len(files) == 1 and files[0].stem == datetime.now(UTC).strftime("%Y-%m-%d")
    line = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert set(line) == set(RECORD_FIELDS) == set(rec)
    assert isinstance(line["ts"], int) and len(line["ts_local"]) == 16
    assert line["bytes"] == 1024 and line["retries"] == 1 and line["failover"] is False
    assert line["duration_ms"] == 12.3


async def test_summary_per_service_and_purpose():
    for svc, purpose, status in (("gee_primary", "s2", "success"), ("gee_primary", "s2", "timeout"),
                                 ("gee_secondary", "s1", "success"), ("openrouter", "report_generation", "success")):
        await record_api_call(run_id=9, service=svc, operation="op", purpose=purpose, status=status,
                              bytes_count=10, failover=svc == "gee_secondary", tokens_in=5, tokens_out=7)
    await record_api_call(run_id=10, service="gee_primary", operation="op", purpose="x")
    calls = read_run_calls(9)
    s = build_usage_summary(9, calls)
    assert s["total_calls"] == 4 and s["failed_calls"] == 1 and s["failover_calls"] == 1
    assert s["tokens_in"] == 20 and s["tokens_out"] == 28
    md = s["markdown"]
    assert "### Xizmatlar boʻyicha" in md and "### Maqsadlar boʻyicha" in md and "| gee_primary | 2 |" in md


def test_purge_logs_older_than_30_days():
    old = (datetime.now(UTC) - timedelta(days=31)).strftime("%Y-%m-%d")
    new = (datetime.now(UTC) - timedelta(days=29)).strftime("%Y-%m-%d")
    (config.API_CALLS_LOG_DIR / f"{old}.jsonl").write_text("{}\n")
    (config.API_CALLS_LOG_DIR / f"{new}.jsonl").write_text("{}\n")
    assert purge_old_logs() == 1
    assert not (config.API_CALLS_LOG_DIR / f"{old}.jsonl").exists()
    assert (config.API_CALLS_LOG_DIR / f"{new}.jsonl").exists()
