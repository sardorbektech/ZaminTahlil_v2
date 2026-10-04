# DECISIONS.md — Arxitektura va Texnik Qarorlar

Bu faylda loyiha davomida qabul qilingan asosiy texnik qarorlar va ularning sabablari qayd etiladi.

---

## 1. Terminal Telemetriyasi va Foydalanuvchi Talabi
- **Qaror:** GEE, sensor va ob-havo qabul qilish bosqichlarida konsolga (terminalga) toza, chiroyli va axborotga boy xabarlar (`[GEE] Qabul qilindi: Sentinel-2 | Scene: ... | Bands: B2,B3,B4,B8 | Vaqt: ...`) chiqariladi.
- **Sabab:** Foydalanuvchi joriy vazifada har bir jarayonni va qaysi sun'iy yo'ldoshdan nimalar kelayotganini terminalda ko'rib turishni qat'iy talab qildi.

## 2. Deterministik Mock GEE Gateway
- **Qaror:** Haqiqiy Google hisob yoki hisob ma'lumotlari mavjud bo'lmaganda yoki avtomatlashtirilgan testlarda `MockGEEGateway` to'liq sintetik lekin fizik jihatdan real raster massivlarni yaratadi.
- **Sabab:** Testlar tarmoqqa bog'lanmasligi, tez ishlashi va barcha chegaraviy holatlarni (429, timeout, failover) ishonchli tekshirishi kerak.

## 3. SQLite STRICT va WAL
- **Qaror:** SQLite jadvallari STRICT kalit so'zi va WAL rejimida ishlaydi.
- **Sabab:** Ma'lumot turlarining qat'iyligini ta'minlash va bir vaqtning o'zida yozish/o'qish operatsiyalarida qulflanishlarning oldini olish.
