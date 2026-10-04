"""Tashqi API chaqiruvlari jurnali (Usage Tracker).

Har bir GEE (asosiy/zaxira) va AI chaqiruvi data/logs/api_calls/YYYY-MM-DD.jsonl fayliga
yoziladi, 30 kun saqlanadi va hech qachon terminalga chiqarilmaydi.
GET /api/v1/usage/runs/{id} uchun Markdown xulosa shu yerda tuziladi.
"""

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.core import config
from backend.app.core.constants import USAGE_LOG_RETENTION_DAYS
from backend.app.core.time import fmt_local, now_ts

# JSONL yozuvining majburiy maydonlari (SIMPLE.md §10) — tartib muhim emas
RECORD_FIELDS = (
    "ts",
    "ts_local",
    "run_id",
    "service",
    "operation",
    "purpose",
    "dataset",
    "request",
    "status",
    "duration_ms",
    "bytes",
    "retries",
    "failover",
    "response",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "error",
)

_write_lock = threading.Lock()


def _log_dir() -> Path:
    return config.API_CALLS_LOG_DIR


def build_record(
    *,
    run_id: int | None,
    service: str,
    operation: str,
    purpose: str,
    dataset: str = "",
    request: str = "",
    status: str = "success",
    duration_ms: float = 0.0,
    bytes_count: int = 0,
    retries: int = 0,
    failover: bool = False,
    response: str = "",
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
    error: str | None = None,
    ts: int | None = None,
) -> dict[str, Any]:
    """Jurnal yozuvini SIMPLE.md §10 sxemasi bo'yicha tuzadi."""
    t = ts if ts is not None else now_ts()
    return {
        "ts": t,
        "ts_local": fmt_local(t),
        "run_id": run_id,
        "service": service,
        "operation": operation,
        "purpose": purpose,
        "dataset": dataset,
        "request": request[:500],
        "status": status,
        "duration_ms": round(float(duration_ms), 1),
        "bytes": int(bytes_count),
        "retries": int(retries),
        "failover": bool(failover),
        "response": response[:500],
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost_usd, 6) if cost_usd is not None else None,
        "error": error[:1000] if error else None,
    }


def write_record(record: dict[str, Any]) -> None:
    """Yozuvni kunlik JSONL fayliga qo'shadi (thread-xavfsiz, sinxron)."""
    day = datetime.fromtimestamp(record["ts"], tz=UTC).strftime("%Y-%m-%d")
    path = _log_dir() / f"{day}.jsonl"
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


async def record_api_call(**kwargs: Any) -> dict[str, Any]:
    """Tashqi API chaqiruvini jurnalga yozadi va yozuvni qaytaradi."""
    rec = build_record(**kwargs)
    write_record(rec)  # kichik fayl yozuvi — event loopni sezilarli to'xtatmaydi
    return rec


def purge_old_logs(max_age_days: int = USAGE_LOG_RETENTION_DAYS) -> int:
    """30 kundan eski JSONL fayllarni o'chiradi."""
    cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
    removed = 0
    for f in _log_dir().glob("*.jsonl"):
        if f.stem < cutoff:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def read_run_calls(run_id: int) -> list[dict[str, Any]]:
    """Berilgan run uchun barcha jurnal yozuvlarini o'qiydi (vaqt bo'yicha tartiblangan)."""
    calls: list[dict[str, Any]] = []
    for path in sorted(_log_dir().glob("*.jsonl")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("run_id") == run_id:
                        calls.append(rec)
        except OSError:
            continue
    calls.sort(key=lambda r: r.get("ts", 0))
    return calls


def max_logged_run_id() -> int:
    """Jurnallardagi eng katta run_id (yangi bazada ID lar takrorlanmasligi uchun)."""
    best = 0
    for path in _log_dir().glob("*.jsonl"):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rid = json.loads(line).get("run_id")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if isinstance(rid, int) and rid > best:
                        best = rid
        except OSError:
            continue
    return best


def _fmt_bytes(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _aggregate(calls: list[dict[str, Any]], key: str) -> list[tuple[str, dict[str, Any]]]:
    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "duration_ms": 0.0, "bytes": 0, "failed": 0, "retries": 0}
    )
    for c in calls:
        a = agg[str(c.get(key) or "—")]
        a["calls"] += 1
        a["duration_ms"] += float(c.get("duration_ms") or 0.0)
        a["bytes"] += int(c.get("bytes") or 0)
        a["retries"] += int(c.get("retries") or 0)
        if c.get("status") != "success":
            a["failed"] += 1
    return sorted(agg.items(), key=lambda kv: -kv[1]["calls"])


def build_usage_summary(run_id: int, calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Run bo'yicha Markdown xulosa: xizmat va maqsad kesimida chaqiruvlar, vaqt, hajm, xatolar."""
    total_ms = sum(float(c.get("duration_ms") or 0.0) for c in calls)
    total_bytes = sum(int(c.get("bytes") or 0) for c in calls)
    failed = sum(1 for c in calls if c.get("status") != "success")
    failovers = sum(1 for c in calls if c.get("failover"))
    tok_in = sum(int(c.get("tokens_in") or 0) for c in calls)
    tok_out = sum(int(c.get("tokens_out") or 0) for c in calls)

    md = [
        f"## Rekognossirovka #{run_id} — tashqi soʻrovlar nazorati",
        "",
        f"- **Jami soʻrovlar:** {len(calls)}",
        f"- **Umumiy vaqt:** {total_ms / 1000.0:.1f} s",
        f"- **Maʼlumot hajmi:** {_fmt_bytes(total_bytes)}",
        f"- **Muvaffaqiyatsiz:** {failed}",
        f"- **Zaxira loyihada bajarilgan:** {failovers}",
        f"- **AI tokenlari:** {tok_in} kirish / {tok_out} chiqish",
        "",
    ]
    for title, key in (("Xizmatlar boʻyicha", "service"), ("Maqsadlar boʻyicha", "purpose")):
        md += [
            f"### {title}",
            "",
            "| Nomi | Soʻrov | Vaqt (s) | Hajm | Xato | Qayta urinish |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, a in _aggregate(calls, key):
            md.append(
                f"| {name} | {a['calls']} | {a['duration_ms'] / 1000.0:.1f} | "
                f"{_fmt_bytes(a['bytes'])} | {a['failed']} | {a['retries']} |"
            )
        md.append("")

    md += [
        "### Soʻrovlar roʻyxati",
        "",
        "| Vaqt | Xizmat | Operatsiya | Maqsad | Holat | ms | Hajm |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for c in calls:
        status = c.get("status", "")
        if c.get("error"):
            status = f"{status}: {str(c['error'])[:60]}".replace("|", "/")
        md.append(
            f"| {c.get('ts_local')} | {c.get('service')} | {c.get('operation')} | "
            f"{c.get('purpose')} | {status} | {c.get('duration_ms')} | "
            f"{_fmt_bytes(int(c.get('bytes') or 0))} |"
        )

    return {
        "run_id": run_id,
        "total_calls": len(calls),
        "total_duration_ms": round(total_ms, 1),
        "total_bytes": total_bytes,
        "failed_calls": failed,
        "failover_calls": failovers,
        "tokens_in": tok_in,
        "tokens_out": tok_out,
        "markdown": "\n".join(md),
        "calls": calls,
    }


async def get_run_usage_summary(run_id: int) -> dict[str, Any]:
    """Berilgan run uchun jurnalni o'qib, xulosani qaytaradi."""
    return build_usage_summary(run_id, read_run_calls(run_id))
