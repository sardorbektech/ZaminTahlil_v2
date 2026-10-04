"""AI hisoboti (SIMPLE.md §8).

- Kirish: faqat raqamli natijalar (summary.json) ixcham JSON ko'rinishida; `images` maydoni bo'sh.
- Har bir barmoq izi uchun ko'pi bilan bitta muvaffaqiyatli hisobot; muvaffaqiyatsiz urinish qayta qilinadi.
"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.ai.client import AIClient, ai_client
from backend.app.core.errors import AIReportError, ConflictError, NotFoundError
from backend.app.core.run_settings import RunSettings
from backend.app.core.time import now_ts
from backend.app.db.enums import JobStatus, ReportStatus
from backend.app.db.models import ReportModel, RunModel

REPORT_SECTIONS = (
    "Umumiy maʼlumot",
    "Relyef",
    "Yer qoplami",
    "Oʻzgarishlar",
    "Ob-havo va taʼsiri",
    "Prognoz va xavflar",
    "Maʼlumot sifati va cheklovlar",
)

SYSTEM_PROMPT = (
    "Siz ZaminTahlil tizimining geo-tahlilchisisiz. Sizga foydalanuvchi tanlagan hudud boʻyicha "
    "sunʼiy yoʻldosh va ob-havo maʼlumotlaridan hisoblangan RAQAMLI natijalar JSON koʻrinishida beriladi.\n\n"
    "Vazifa: shu raqamlar asosida oʻzbek tilida (lotin yozuvi; oʻ va gʻ da ʻ (U+02BB), tutuq belgisi ʼ (U+02BC)) "
    "Markdown hisobot yozish.\n\n"
    "QATʼIY QOIDALAR:\n"
    "1. Faqat JSON dagi qiymatlarga tayaning. Hech qanday fakt, raqam, joy nomi yoki sabab toʻqimang.\n"
    "2. Har bir sanani JSON dagi `*_local` koʻrinishida (DD.MM.YYYY HH:MM, Toshkent vaqti) keltiring.\n"
    "3. Qiymat null boʻlsa yoki maʼlumot berilmagan boʻlsa — \"maʼlumot yoʻq\" deb yozing, taxmin qilmang.\n"
    "4. `low_confidence: true`, `quality_flag` GOOD boʻlmagan yoki \"(ehtimoliy)\" sinflarni \"past ishonchlilik\" "
    "yoki \"noaniq\" deb aniq belgilang.\n"
    "5. Har bir muhim raqam yonida uning manbasini (sensor/dataset) koʻrsating.\n"
    "6. Javob faqat Markdown matn boʻlsin: JSON yoki ``` kod bloki emas. Faqat lotin alifbosi — kirill yoki "
    "boshqa tillardagi soʻzlar ishlatilmasin.\n"
    "7. Hisobot aynan quyidagi 7 boʻlimdan iborat boʻlsin (## sarlavha bilan, shu tartibda):\n"
    + "\n".join(f"   ## {i}. {s}" for i, s in enumerate(REPORT_SECTIONS, 1))
)


FORMAT_FIX_PROMPT = (
    "Javobingiz talab qilingan formatda emas. Faqat Markdown matn yozing (JSON emas, ``` blokisiz) va "
    "aynan 7 ta boʻlimni ## sarlavhalar bilan shu tartibda bering: "
    + "; ".join(f"## {i}. {s}" for i, s in enumerate(REPORT_SECTIONS, 1))
    + ". Yuqoridagi JSON maʼlumotlardan tashqari hech narsa qoʻshmang."
)
MAX_FORMAT_ATTEMPTS = 2


def missing_sections(md: str) -> list[str]:
    """Markdown hisobotda yetishmayotgan majburiy bo'limlar (## sarlavha sifatida)."""
    import re

    text = md.strip()
    if text.startswith("```") or text.startswith("{"):
        return list(REPORT_SECTIONS)
    def norm(x: str) -> str:
        # Apostrof ko'rinishlari (ʼ ʻ ' ’ ‘ `) va * belgilari farq qilmasin
        return re.sub(r"[ʼʻ'’‘`*]", "", x).strip().lower()

    heads = [norm(re.sub(r"^#+\s*(\d+[.)]\s*)?", "", ln)) for ln in text.splitlines() if ln.lstrip().startswith("#")]
    return [s for s in REPORT_SECTIONS if not any(h.startswith(norm(s)) for h in heads)]


def build_ai_payload(summary: dict[str, Any]) -> dict[str, Any]:
    """summary.json dan AI uchun ixcham kirish (faqat raqamlar va vaqtlar)."""
    keys = (
        "run",
        "sources",
        "observations",
        "class_areas",
        "stats_by_date",
        "terrain",
        "soil_moisture",
        "changes",
        "cross_check",
        "weather",
        "weather_impact",
        "quality_flags",
    )
    payload = _compact({k: summary.get(k) for k in keys})
    # Qatlam statistikasidan faqat asosiy qiymatlar (token tejash)
    sbd = payload.get("stats_by_date") or {}
    for name, rows in sbd.items():
        sbd[name] = [
            {k: r.get(k) for k in ("acq_time_local", "prev_time_local", "mean", "min", "max", "valid_pct", "quality_flag", "unit")
             if r.get(k) not in (None, "", "GOOD")}
            for r in rows
        ]
    payload["images"] = []  # kelajak uchun; hozir ishlatilmaydi
    return payload


def _compact(obj: Any) -> Any:
    """`*_ts` (epoch) kalitlarini olib tashlaydi — AI faqat `*_local` sanalardan foydalanadi."""
    if isinstance(obj, dict):
        return {k: _compact(v) for k, v in obj.items() if not (k.endswith("_ts") or k == "ts")}
    if isinstance(obj, list):
        return [_compact(v) for v in obj]
    return obj


def build_user_prompt(summary: dict[str, Any]) -> str:
    compact = json.dumps(build_ai_payload(summary), ensure_ascii=False, separators=(",", ":"), default=str)
    return f"Rekognossirovka natijalari (JSON):\n{compact}\n\nYuqoridagi qoidalarga qatʼiy amal qilib hisobot yozing."


async def generate_report_for_run(
    session: AsyncSession,
    run: RunModel,
    summary: dict[str, Any],
    run_settings: RunSettings,
    client: AIClient | None = None,
) -> ReportModel:
    """Run uchun hisobot yaratadi (barmoq izi bo'yicha bir marta).

    Raises:
        ConflictError: shu barmoq izi uchun muvaffaqiyatli hisobot allaqachon bor.
        AIReportError: provayder xatosi (urinish FAILED sifatida saqlanadi, keyin qayta urinish mumkin).
    """
    if run.fingerprint is None or run.status != JobStatus.COMPLETED:
        raise NotFoundError("Hisobot uchun yakunlangan rekognossirovka topilmadi.")
    client = client or ai_client
    existing = (
        await session.execute(select(ReportModel).where(ReportModel.fingerprint == run.fingerprint))
    ).scalars().first()
    if existing is not None and existing.status == ReportStatus.OK:
        raise ConflictError(
            "Bu maʼlumotlar uchun hisobot allaqachon tayyorlangan. Yangi hisobot faqat yangi sunʼiy yoʻldosh maʼlumoti kelganda tuziladi.",
            code="REPORT_EXISTS",
        )

    provider, model = run_settings.ai_provider, run_settings.ai_model
    report = existing or ReportModel(
        run_id=run.id,
        fingerprint=run.fingerprint,
        status=ReportStatus.FAILED,
        provider=provider,
        model=model,
        attempts=0,
        created_at=now_ts(),
    )
    if existing is None:
        session.add(report)
    report.attempts = (report.attempts or 0) + 1
    report.provider, report.model = provider, model
    try:
        prompt = build_user_prompt(summary)
        content = ""
        for _ in range(MAX_FORMAT_ATTEMPTS):
            content = await client.generate(
                provider=provider,
                model=model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                history_key=run.fingerprint.hex(),
                history_size=run_settings.ai_history_size,
                run_id=run.id,
            )
            if not missing_sections(content):
                break
            prompt = FORMAT_FIX_PROMPT  # oldingi javob tarixda qoladi (history window)
        else:
            raise AIReportError(
                "AI javobi talab qilingan formatda emas (7 ta boʻlimli Markdown kutilgan edi).",
                code="AI_BAD_FORMAT",
            )
    except AIReportError as e:
        report.status = ReportStatus.FAILED
        report.error = e.message_uz
        report.created_at = now_ts()
        await session.commit()
        raise
    report.status = ReportStatus.OK
    report.content_md = content
    report.error = None
    report.created_at = now_ts()
    await session.commit()
    return report
