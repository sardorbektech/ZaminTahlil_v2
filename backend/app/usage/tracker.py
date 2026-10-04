"""Tashqi API chaqiruvlari auditi va nazorati moduli (Usage Tracker).

Har bir GEE va AI chaqiruvi data/logs/api_calls/YYYY-MM-DD.jsonl fayliga yoziladi.
GET /api/v1/usage/runs/{id} uchun Markdown xulosasi shakllantiriladi.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.core.config import API_CALLS_LOG_DIR
from backend.app.core.time import fmt_local, now_ts

_log_lock = asyncio.Lock()


async def record_api_call(
    run_id: int | None,
    service: str,  # "gee_primary", "gee_secondary", "openrouter", "openai", "ollama"
    operation: str,  # "computePixels", "listScenes", "chat/completions"
    purpose: str,  # "optical_download", "sar_download", "report_generation"
    dataset: str = "",
    request_summary: str = "",
    status: str = "success",  # "success", "error", "timeout", "failover"
    duration_ms: float = 0.0,
    bytes_count: int = 0,
    retries: int = 0,
    failover: bool = False,
    response_summary: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    error: str | None = None,
) -> None:
    """Tashqi API chaqiruvini JSONL fayliga qo'shadi."""
    ts = now_ts()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    log_file = API_CALLS_LOG_DIR / f"{date_str}.jsonl"

    record = {
        "ts": ts,
        "ts_local": fmt_local(ts),
        "run_id": run_id,
        "service": service,
        "operation": operation,
        "purpose": purpose,
        "dataset": dataset,
        "request": request_summary,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "bytes": bytes_count,
        "retries": retries,
        "failover": failover,
        "response": response_summary,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost_usd, 6),
        "error": error,
    }

    line = json.dumps(record, ensure_ascii=False) + "\n"
    async with _log_lock:
        await asyncio.to_thread(_append_file, log_file, line)


def _append_file(path: Path, text_content: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text_content)


async def get_run_usage_summary(run_id: int) -> dict[str, Any]:
    """Berilgan vazifa (run_id) uchun barcha chaqiruvlarni o'qib, Markdown xulosasini tuzadi."""
    calls: list[dict[str, Any]] = []

    # So'nggi 30 kunlik jsonl fayllarni ko'rib chiqish
    files = sorted(API_CALLS_LOG_DIR.glob("*.jsonl"), reverse=True)
    for file_path in files[:30]:
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if rec.get("run_id") == run_id:
                        calls.append(rec)
        except Exception:
            continue

    total_calls = len(calls)
    total_duration_ms = sum(c.get("duration_ms", 0.0) for c in calls)
    total_bytes = sum(c.get("bytes", 0) for c in calls)
    failed_calls = sum(1 for c in calls if c.get("status") != "success")
    failover_count = sum(1 for c in calls if c.get("failover") is True)
    total_tokens = sum(c.get("tokens_in", 0) + c.get("tokens_out", 0) for c in calls)

    # Markdown hisobotini shakllantirish
    md_lines = [
        f"## Rekognossirovka #{run_id} — API Foydalanish Nazorati\n",
        f"- **Jami tashqi soʻrovlar:** {total_calls}",
        f"- **Umumiy vaqt:** {total_duration_ms / 1000.0:.2f} soniya",
        f"- **Yuklangan maʼlumot hajmi:** {total_bytes / (1024 * 1024):.2f} MB",
        f"- **Xatoliklar soni:** {failed_calls}",
        f"- **Zaxiraga oʻtishlar (Failovers):** {failover_count}",
        f"- **AI tokenlari:** {total_tokens}\n",
        "### Xizmatlar va Maqsadlar Boʻyicha Taqsimot\n",
        "| Xizmat | Operatsiya | Maqsad | Holat | Vaqt (ms) | Hajm (KB) |",
        "|---|---|---|---|---|---|",
    ]

    for c in calls:
        kb = c.get("bytes", 0) / 1024.0
        md_lines.append(
            f"| {c.get('service')} | {c.get('operation')} | {c.get('purpose')} | {c.get('status')} | {c.get('duration_ms')} | {kb:.1f} |"
        )

    return {
        "run_id": run_id,
        "total_calls": total_calls,
        "total_duration_ms": total_duration_ms,
        "total_bytes": total_bytes,
        "failed_calls": failed_calls,
        "markdown_report": "\n".join(md_lines),
        "calls": calls,
    }
