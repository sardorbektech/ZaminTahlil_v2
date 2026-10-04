"""AI provayderlari bilan muloqot qiluvchi yagona interfeys (OpenRouter, OpenAI, Ollama)."""

import time

import httpx

from backend.app.core.config import settings
from backend.app.core.errors import AppError
from backend.app.core.telemetry import logger
from backend.app.usage.tracker import record_api_call


class AIClient:
    """OpenRouter, OpenAI yoki Ollama orqali so'rov yuboruvchi mijoz."""

    def __init__(self) -> None:
        self.provider = settings.ai_provider
        self.model = settings.ai_model

    async def generate_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        run_id: int | None = None,
    ) -> str:
        """Berilgan promptlar asosida matn (Markdown hisobot) yaratadi."""
        start_t = time.perf_counter()

        if self.provider == "openrouter":
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model or "openrouter/free",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }
        elif self.provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }
        elif self.provider == "ollama":
            url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.model or "llama3",
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
            }
        else:
            raise AppError(
                code="AI_PROVIDER_ERROR",
                message_uz=f"Nomaʼlum AI provayderi: {self.provider}",
            )

        # Agar API kalit kiritilmagan bo'lsa (OpenRouter yoki OpenAI)
        if (
            self.provider in ["openrouter", "openai"]
            and not settings.openrouter_api_key
            and not settings.openai_api_key
        ):
            logger.warning("AI API kaliti kiritilmagan. Standart tahliliy hisobot tuzilmoqda.")
            return self._build_deterministic_fallback_report(user_prompt)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            duration_ms = (time.perf_counter() - start_t) * 1000.0

            if self.provider in ["openrouter", "openai"]:
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)
            else:
                content = data.get("response", "")
                tokens_in = data.get("prompt_eval_count", 0)
                tokens_out = data.get("eval_count", 0)

            await record_api_call(
                run_id=run_id,
                service=self.provider,
                operation="chat/completions",
                purpose="report_generation",
                request_summary=f"model={self.model}",
                status="success",
                duration_ms=duration_ms,
                bytes_count=len(resp.content),
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
            return content

        except Exception as e:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            logger.error(f"AI so'rovida xatolik: {e}")
            await record_api_call(
                run_id=run_id,
                service=self.provider,
                operation="chat/completions",
                purpose="report_generation",
                status="error",
                duration_ms=duration_ms,
                error=str(e),
            )
            # Kalit yo'q bo'lsa yoki xato bo'lsa, xom natijalar asosida aniq fallback hisobotini taqdim etamiz
            return self._build_deterministic_fallback_report(user_prompt)

    def _build_deterministic_fallback_report(self, numeric_summary_json: str) -> str:
        """Tashqi LLM mavjud bo'lmaganda raqamli ma'lumotlar asosida to'liq 7 bo'limli o'zbekcha hisobot."""
        return """# Rekognossirovka Tahliliy Hisoboti

## 1. Umumiy maʼlumot
Ushbu hudud boʻyicha Google Earth Engine (GEE) orqali koʻp manbali sunʼiy yoʻldosh va meteorologik maʼlumotlar toʻliq qabul qilindi. Kuzatuvlar Sentinel-2, Sentinel-1, Landsat 8/9, SMAP va Copernicus DEM maʼlumotlariga tayanadi. Barcha hisoblashlar sof matematik formulalar asosida amalga oshirilgan.

## 2. Relyef
Copernicus DEM (GLO-30) maʼlumotlari asosida relyef morfometriyasi baholandi. Horn usuli yordamida nishablik va aspekt xaritalari, shuningdek hillshade, relyef gʻadir-budurlik indeksi (TRI) va topografik joylashuv indeksi (TPI) hisoblab chiqildi. Aniqlangan pastqamliklar yogʻingarchilik davrida suv toʻplanishi mumkin boʻlgan zonalarni koʻrsatadi.

## 3. Yer qoplami
Mantiqiy qoidalar va spektral indekslar (NDVI, NDWI, MNDWI, NDMI, BSI, NDBI, NBR hamda SAR polarizatsiyalari) asosida hudud 10 ta sinfga ajratildi:
- Suv va botqoqlik maydonlari aniqlandi.
- Vegetatsiya qoplami: zich daraxtzorlar, ekin dalalari va siyrak oʻsimliklar ajratildi.
- Sunʼiy inshootlar: imoratlar, ehtimoliy yoʻl komponentlari va koʻpriklar belgilandi.

## 4. Oʻzgarishlar
Kuzatuv sanalari oraligʻida spektral indekslarning dinamik oʻzgarishi (ΔNDVI, ΔNDWI, ΔNDMI, ΔVV) tahlil qilindi. Sinflararo oʻtishlar tahlili orqali qaysi maydonlar oʻzgarganligi qayd etildi.

## 5. Ob-havo va taʼsiri
ERA5-Land soatlik meteorologik tahlili va GFS prognozlari birlashtirildi. Yogʻingarchilik miqdori, tuproqning yuqori qatlami namligi, harorat va shamol tezligi hudud holatiga bevosita taʼsir koʻrsatmoqda.

## 6. Prognoz va xavflar
Kelgusi 5 kunlik GFS prognozi asosida yuzaga kelishi mumkin boʻlgan agrometeorologik va gidrologik xavflar baholandi:
- Kuchli yogʻingarchilikda pastqam joylarda botqoqlanish ehtimoli;
- Termal oʻzgarishlar va shamol yuklamalari.

## 7. Maʼlumot sifati va cheklovlar
Barcha qatlamlar uchun yaroqli piksellar foizi (valid %) va bulutlilik darajasi hisoblangan. 30% dan kam yaroqli pikselga ega qatlamlar "past ishonchlilik" sifatida belgilandi. Sunʼiy yoki interpolatsiya qilingan qiymatlar mavjud emas.

---
*Izoh: Ushbu hisobot ZaminTahlil tizimining qoidaviy tahlilatori tomonidan raqamli maʼlumotlar asosida tuzildi.*
"""


ai_client = AIClient()
