"""AI hisobotini shakllantiruvchi modul.

Raqamli tahlil natijalarini ixcham JSON formatida tayyorlab,
LLM ga 7 ta majburiy bo'limdan iborat o'zbek tilidagi hisobot tuzish buyrug'ini beradi.
"""

import json
from typing import Any

from backend.app.ai.client import ai_client
from backend.app.core.time import fmt_local

SYSTEM_PROMPT = """Siz ZaminTahlil tizimining professional geo-analitigi va rekognossirovka ekspertisiz.
Sizga foydalanuvchi tanlagan hudud boʻyicha oʻlchangan va hisoblangan aniq raqamli maʼlumotlar (JSON shaklida) beriladi.

SIZNING VAZIFANGIZ:
Ushbu raqamli koʻrsatkichlar asosida oʻzbek tilida (lotin yozuvida, oʻ/gʻ harflarida ʻ U+02BB va tutuq belgisi ʼ U+02BC dan foydalanib) professional tahliliy Markdown hisobot yozish.

QATʼIY QOIDALAR:
1. Hech qanday maʼlumot yoki faktni toʻqimang (hallucination taqiqlanadi). Faqat berilgan JSON raqamlariga tayaning.
2. Barcha sanalarni "DD.MM.YYYY HH:MM" formatida keltiring.
3. Noaniq yoki past ishonchlilikka ega boʻlgan koʻrsatkichlarni "aniq emas" yoki "past ishonchlilik" deb aniq belgilang.
4. Hisobot quyidagi 7 ta boʻlimdan qatʼiy iborat boʻlishi shart:
   ## 1. Umumiy maʼlumot
   ## 2. Relyef
   ## 3. Yer qoplami
   ## 4. Oʻzgarishlar
   ## 5. Ob-havo va taʼsiri
   ## 6. Prognoz va xavflar
   ## 7. Maʼlumot sifati va cheklovlar
"""


async def generate_recon_report(
    summary_data: dict[str, Any],
    run_id: int | None = None,
) -> str:
    """Raqamli ma'lumotlar asosida Markdown hisobot yaratadi."""
    # Ixcham JSON tuzish
    compact_payload = {
        "run_id": summary_data.get("run_id"),
        "area_km2": summary_data.get("area_km2"),
        "created_at_local": fmt_local(summary_data.get("created_at")),
        "scenes": summary_data.get("scenes", []),
        "classes": summary_data.get("classes", []),
        "layer_stats": summary_data.get("layer_stats", {}),
        "terrain": summary_data.get("terrain", {}),
        "changes": summary_data.get("changes", []),
        "weather_impact": summary_data.get("weather_impact", []),
        "quality_flags": summary_data.get("quality_flags", {}),
        "images": [],  # Kelgusida foydalanish uchun bo'sh
    }

    user_prompt = f"""Quyidagi rekognossirovka maʼlumotlari boʻyicha hisobot tayyorlang:
```json
{json.dumps(compact_payload, ensure_ascii=False, indent=2)}
```
"""

    report_markdown = await ai_client.generate_completion(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        run_id=run_id,
    )
    return report_markdown
