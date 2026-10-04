# ABOUT.md — ZaminTahlil v2 Tizimining Toʻliq Texnik va Mantiqiy Tavsifi

ZaminTahlil — foydalanuvchi xaritada tanlagan istalgan yer maydoni (toʻgʻri toʻrtburchak yoki erkin koʻpburchak shaklida, 100 kvadrat kilometrgacha) boʻyicha kompleks rekognossirovka (atroflicha fazoviy razvedka va tahlil) oʻtkazuvchi dasturiy majmuadir.

Tizim Google Earth Engine (GEE) platformasi orqali Yerni masofadan zondlovchi yetakchi sunʼiy yoʻldoshlar (Sentinel-2, Sentinel-1, Landsat 8/9, Copernicus DEM, SMAP) hamda global ob-havo xizmatlarining (ERA5-Land, GFS, CHIRPS) maʼlumotlarini avtomatik yuklab oladi. Yuklangan xom maʼlumotlar sof matematik va fizik formulalar yordamida tahlil qilinadi: oʻsimlik qoplami, namlik, suv havzalari, relyef nishabligi, yer sathi harorati, sunʼiy inshootlar va yer turlari aniqlanadi. Yakunda katta til modeli (LLM) barcha raqamli natijalarni jamlab, mutaxassis darajasidagi batafsil oʻzbekcha tahliliy hisobot tuzib beradi hamda maydon boʻyicha savol-javob chatini taqdim etadi.

Ushbu hujjatda loyihaning arxitekturasi, ishlash tamoyillari, har bir alohida qiymat va qatlamning fizik-matematik mohiyati hamda tizimda kechadigan barcha jarayonlar kod parchalarisiz, toʻliq va tushunarli tilda yoritilgan.

---

## 1. Asosiy Falsafa va Oʻzgarmas Qoidalar

Tizimning barcha qismlari bitta bosh maqsadga xizmat qiladi: **foydalanuvchiga tanlangan hudud boʻyicha eng aniq, toʻliq va har bir oʻlchovi vaqt bilan tasdiqlangan maʼlumotlarni taqdim etish**.

1. **Mutlaq aniqlik (soxta maʼlumot taqiqlanadi):** Tizimda sunʼiy (fake/mock), taxmin qilingan yoki oraliq toʻqib chiqarilgan (interpolatsiya qilingan) maʼlumotlar mutlaqo ishlatilmaydi. Agar sunʼiy yoʻldosh bulut tufayli maʼlumot bermagan boʻlsa yoki ob-havo stansiyasida raqam boʻlmasa, u nol yoki taxminiy qiymat qilib koʻrsatilmaydi, balki toʻgʻridan-toʻgʻri "maʼlumot yoʻq" deb belgilanadi.
2. **Har bir raqamning pasporti bor:** Ekranda yoki hisobotda koʻrsatiladigan har bir son qaysi sunʼiy yoʻldoshdan olingani, qaysi formula bilan hisoblangani va aynan qaysi soniya/soatda oʻlchangani (Toshkent vaqti bilan) bilan birga saqlanadi.
3. **Bitta vaqtda bitta tahlil:** Resurslarni asrash va hisoblash quvvatini toʻgʻri taqsimlash uchun serverda bir vaqtning oʻzida faqat bitta rekognossirovka jarayoni bajariladi. Boshqa foydalanuvchilar navbat kutadi.
4. **Istalgan vaqtda toʻxtatish imkoniyati:** Foydalanuvchi "Toʻxtatish" tugmasini bossa, tizim 2 soniya ichida barcha tarmoq soʻrovlarini toʻxtatadi, hisoblash xotirasini tozalaydi va vaqtinchalik fayllarni oʻchirib yuboradi.
5. **Sahifa siljimaydi (No-scroll):** Interfeys ixcham boshqaruv paneli sifatida qurilgan: butun sahifa brauzer oynasida qotib turadi, uzun jadvallar va hisobotlar esa panel ichida tartibli varaqlanadi yoki aylanadi.

---

## 2. Foydalanuvchilar va Maydonlarni Saqlash Mexanizmi

- **Tokenlarsiz yengil kirish:** Tizimda murakkab roʻyxatdan oʻtish bosqichlari yoʻq. Foydalanuvchi oʻziga login va parol oʻylab topadi. Birinchi marta kiritilgan login avtomatik tarzda yangi profil sifatida ochiladi. Agar login mavjud boʻlsa, paroli tekshiriladi.
- **Parol xavfsizligi:** Parollar maʼlumotlar bazasida ochiq saqlanmaydi. Ular xalqaro kriptografik standart (PBKDF2-HMAC-SHA256 algoritmi, 200 ming martalik qorishma va tasodifiy tuzlama) asosida himoyalangan.
- **Shaxsiy hududlar (Ownership):** Har bir tahlil qilingan maydon uni yaratgan foydalanuvchiga tegishli boʻladi. Hech bir begona shaxs boshqasining maydonlarini, uning xaritalarini yoki hisobotlarini koʻra olmaydi.
- **"Mening maydonlarim":** Muvaffaqiyatli yakunlangan har bir tahlil doimiy saqlanadi. Foydalanuvchi istalgan paytda oʻzining avvalgi maydonlari roʻyxatini ochishi, nomini oʻzgartirishi, qaytadan koʻrishi yoki oʻchirib tashlashi mumkin.
- **Baza yoʻqolsa ham tizim mustahkam:** Agar maʼlumotlar bazasi fayli tasodifan oʻchib ketsa ham, dastur ishga tushganda avtomatik ravishda toza yangi baza yaratadi, diskdagi jurnallardan oxirgi raqamlar tartibini oladi va foydalanuvchini muammosiz qayta tiklaydi.

---

## 3. Tizim Qaysi Sunʼiy Yoʻldosh va Manbalardan Foydalanadi?

ZaminTahlil bir nechta mustaqil koinot apparatlari va meteorologik markazlar maʼlumotlarini birlashtiradi:

1. **Sentinel-2 (Yevropa Kosmik Agentligi — ESA):**
   - *Vazifasi:* Asosiy optik koʻrinish, tabiiy ranglar (RGB), oʻsimliklar holati, namlik va yer qoplamini aniqlash.
   - *Imkoniyati:* Yerni 10–20 metrli yuqori aniqlikda, har 5 kunda suratga oladi. Infraqizil va qizil nurlar diapazonida oʻsimliklarning yashillik darajasini koʻrsatadi.
2. **Sentinel-1 (ESA):**
   - *Vazifasi:* Radar (SAR) orqali yer yuzasini zondlash.
   - *Imkoniyati:* Optik kameralardan farqli oʻlaroq, radar nurlari quyuq bulutlar, tuman va tun pardasini teshib oʻtadi. Suv havzalari, botqoqliklar, nam tuproq va metall/beton inshootlarni aniqlashda tengsizdir.
3. **Landsat 8 va Landsat 9 (NASA / USGS):**
   - *Vazifasi:* Termal tahlil va optik tekshiruv.
   - *Imkoniyati:* Yer sathi haroratini (LST) Selsiy shkalasida oʻlchaydi. Shuningdek, Sentinel-2 koʻrsatkichlarini mustaqil tekshirib, xatoliklarni bartaraf etish uchun qoʻshimcha nazorat vazifasini bajaradi.
4. **Copernicus DEM (GLO-30):**
   - *Vazifasi:* Raqamli relyef modeli.
   - *Imkoniyati:* Yer yuzasining dengiz sathidan balandligi, qiyalik burchaklari, tepaliklar, jarliklar va suv toʻplanishi mumkin boʻlgan pastqamliklarni 30 metrli aniqlikda koʻrsatadi.
5. **SMAP (NASA):**
   - *Vazifasi:* Tuproq namligini global oʻlchash.
   - *Imkoniyati:* Tuproqning ustki qatlami va ildiz chuqurligidagi namlik miqdorini fazodan oʻlchaydi.
6. **Ob-havo manbalari:**
   - *ERA5-Land (Yevropa Oʻrta Muddatli Ob-havo Markazi):* Oʻtgan kunlar va soatlar boʻyicha aniq havo harorati, shudring nuqtasi, yogʻin miqdori va shamol tezligi.
   - *GFS (AQSH Milliy Okean va Atmosfera Boshqarmasi — NOAA):* Yaqin soatlardagi ob-havo tahlili hamda kelgusi kunlar uchun yogʻin, harorat va shamol prognozlari.
   - *CHIRPS:* Sunʼiy yoʻldosh va yer stansiyalari orqali tasdiqlangan kunlik yogʻinlar hisobi.

---

## 4. Tizimda Hisoblanadigan Barcha Qiymatlar, Qatlamlar va Parametrlar Ensiklopediyasi

Tizimda koʻrsatiladigan har bir qiymat qanday hisoblanishi, nima maqsadda ishlatilishi, uning fizik mohiyati hamda **yangi yozilganmi yoki tayyor shablon qoidalaridan foydalanilganmi** degan savolga quyida toʻliq javob berilgan.

### 4.1. Optik Spektral Indekslar (Sentinel-2)

Bu indekslar tayyor olingan xarita emas, balki sunʼiy yoʻldoshning turli spektral nurlar (koʻk, yashil, qizil, yaqin infraqizil, qisqa toʻlqinli infraqizil) boʻyicha yorugʻlikni aks ettirish koeffitsiyentlaridan **loyiha ichida noldan sof matematik formulalar yordamida** hisoblanadi.

- **NDVI (Normalized Difference Vegetation Index — Normallashtirilgan Oʻsimlik Indeksi):**
  - *Formulasi:* (Yaqin infraqizil − Qizil) / (Yaqin infraqizil + Qizil).
  - *Fizik mohiyati:* Sogʻlom oʻsimlik bargidagi xlorofill qizil nurni kuchli yutadi (fotosintez uchun) va yaqin infraqizil nurni juda kuchli qaytaradi. Qiymat −1 dan +1 gacha boʻladi.
  - *Amaliy maʼnosi:* 0.1 dan pasti — tosh, tuproq yoki suv; 0.2–0.4 — siyrak oʻtlar; 0.6 dan yuqorisi — gʻovlagan ekinlar va qalin oʻrmonlar. Oʻsimliklarning rivojlanish bosqichini koʻrsatadi.
- **EVI (Enhanced Vegetation Index — Kengaytirilgan Oʻsimlik Indeksi):**
  - *Formulasi:* Yaqin infraqizil va qizil nurlar farqini koʻk nur yordamida atmosfera tumanidan tozalovchi hamda tuproq shovqinini yoʻqotuvchi koʻp koeffitsiyentli formula.
  - *Fizik mohiyati:* NDVI oʻsimliklar juda qalin boʻlib ketganda (oʻrmonlarda) sezgirligini yoʻqotib, "toʻyinib" qoladi. EVI hatto eng qalin changalzorlarda ham oʻsimlik zichligini toʻgʻri ajratib beradi.
- **NDRE (Normalized Difference Red Edge — Qizil Chegara Indeksi):**
  - *Formulasi:* (Yaqin infraqizil − Qizil chegara nuri) / (Yaqin infraqizil + Qizil chegara nuri).
  - *Fizik mohiyati:* Qizil nur bilan infraqizil nur oraligʻidagi oʻtish chegarasi (Red Edge) barglardagi sof xlorofill miqdoriga oʻta sezgir.
  - *Amaliy maʼnosi:* Ekinlarning ozuqa (ayniqsa azot) yetishmovchiligini va erta kasallanishini oddiy koʻz yoki NDVI ilgʻashidan oldin aniqlaydi.
- **NDWI (Normalized Difference Water Index — Suv Indeksi):**
  - *Formulasi:* (Yashil nur − Yaqin infraqizil) / (Yashil nur + Yaqin infraqizil).
  - *Fizik mohiyati:* Suv yuzasi yashil nurni yaxshi qaytaradi, infraqizil nurni esa deyarli toʻliq yutadi.
  - *Amaliy maʼnosi:* Ochiq suv havzalari, daryolar, koʻllar va kanallarni quruqlikdan keskin ajratib koʻrsatadi.
- **MNDWI (Modified NDWI — Modifikatsiyalangan Suv Indeksi):**
  - *Formulasi:* (Yashil nur − Qisqa toʻlqinli infraqizil SWIR1) / (Yashil nur + SWIR1).
  - *Fizik mohiyati:* Oddiy NDWI baʼzan shahar binolari va asfaltni suv bilan adashtirib yuborishi mumkin. MNDWI qisqa toʻlqinli infraqizil nurdan foydalanib, binolar shovqinini bostiradi va suv chegaralarini xatosiz chizadi.
- **NDMI (Normalized Difference Moisture Index — Barg Namligi Indeksi):**
  - *Formulasi:* (Yaqin infraqizil − Qisqa toʻlqinli infraqizil SWIR1) / (Yaqin infraqizil + SWIR1).
  - *Fizik mohiyati:* Barglar toʻqimasidagi suv miqdori qisqa toʻlqinli infraqizil nurning yutilishiga bevosita bogʻliq.
  - *Amaliy maʼnosi:* Oʻsimliklarning suvga qonqanlik darajasini va qurgʻoqchilik stressini koʻrsatadi.
- **NBR (Normalized Burn Ratio — Yongʻin va Kuyish Indeksi):**
  - *Formulasi:* (Yaqin infraqizil − Uzoq qisqa toʻlqinli infraqizil SWIR2) / (Yaqin infraqizil + SWIR2).
  - *Fizik mohiyati:* Tirik oʻsimliklar infraqizilni qaytaradi, kuygan kul va qoraygan tuproq esa uni yutadi va SWIR2 nurini koʻproq aks ettiradi.
  - *Amaliy maʼnosi:* Yongʻin sodir boʻlgan joylar, qamish yoki angʻiz yoqilgan maydonlarni fosh qiladi.
- **NDBI (Normalized Difference Built-up Index — Shaharsozlik / Bino Indeksi):**
  - *Formulasi:* (SWIR1 − Yaqin infraqizil) / (SWIR1 + Yaqin infraqizil).
  - *Fizik mohiyati:* Beton, shifer, gʻisht va asfalt infraqizil nurga nisbatan SWIR nurida yorqinroq koʻrinadi.
  - *Amaliy maʼnosi:* Qurilgan hududlar, sanoat inshootlari, yoʻllar va turar-joy massivlarini aniqlaydi.
- **BSI (Bare Soil Index — Yalangʻoch Tuproq Indeksi):**
  - *Formulasi:* Qisqa toʻlqinli infraqizil va qizil nurlar yigʻindisidan infraqizil va koʻk nurlarni ayirish orqali hisoblanadigan kompozit indeks.
  - *Fizik mohiyati:* Oʻsimliksiz boʻsh yotgan yerni, haydalgan shudgorni, toshloq va qumloq yerlarni oʻsimliklar va binolardan ajratib beradi.

### 4.2. Ranglar, Optik Tekstura va Sifat Koʻrsatkichlari

- **Tabiiy Ranglar (RGB):** Sentinel-2 ning qizil (B4), yashil (B3) va koʻk (B2) kanallari birlashtirilib, inson koʻzi koinotdan qanday koʻrsa, xuddi shunday tabiiy fotosurat yaratiladi.
- **Soxta Rang (False Color Infrared):** Yaqin infraqizil (B8), qizil (B4) va yashil (B3) kanallari birlashtiriladi. Unda oʻsimliklar qizil rangda, suv qora rangda, binolar esa kulrang-moviy boʻlib koʻrinadi. Bu agronomlar uchun oʻsimliklar zichligini koʻrishda eng qulay tasvirdir.
- **Yorqinlik (Brightness):** Koʻrinadigan uchala nurning oʻrtacha intensivligi.
- **Yashil Xromatiklik (Green Chromaticity) va ExG (Excess Green):** Umumiy yorugʻlik ichida aynan yashil nurning ustunlik qilish nisbati.
- **Mahalliy Tekstura (Texture):** Har bir piksel atrofidagi 5x5 katakchali maydonda yorqinlikning oʻrtacha kvadratik chetlanishi (standart ogʻishi) hisoblanadi. Tekis dalalarda tekstura nolga yaqin boʻladi, daraxtzorlar va binolarda esa soya-yorugʻlik keskin almashgani uchun tekstura juda baland boʻladi.
- **Cloud Score+ (cs_cdf):** Google kompaniyasining sunʼiy yoʻldosh tasvirlaridagi har bir pikselning bulutsiz boʻlish ehtimolini baholovchi modeli. Agar ehtimollik 0.60 dan past boʻlsa, piksel bulut deb tahlildan chetlatiladi.
- **SCL (Scene Classification Layer):** ESA tomonidan Sentinel-2 sunʼiy yoʻldoshida hisoblanadigan sinflar qatlami. Bizning algoritm oʻzining hisoblashlari toʻgʻriligini tekshirish uchun ushbu qatlamdan nazorat mezoni sifatida foydalanadi.

### 4.3. Radar Koʻrsatkichlari (Sentinel-1 SAR)

Radar qorongʻida ham, bulutli havoda ham ishlaydi. Uning nurlari yerga urilib qaytadi (Backscatter) va desibellarda (dB) oʻlchanadi. Bu tahlillar ham loyiha ichida maxsus matematik filtrlar bilan hisoblanadi:

- **Li filtri (Lee Filter 5x5):** Radar tasvirlarida tasodifiy toʻlqinlar aralashuvi natijasida mayda "shovqinlar" (speckle) hosil boʻladi. Tizim chiziqli quvvat fazosida 5x5 darcha boʻyicha Li filtrini qoʻllab, tasvirning qirralarini (daryo, yoʻl chegaralarini) buzmasdan shovqinlarni tozalaydi.
- **SAR VV (Vertikal joʻnatilib, vertikal qaytgan toʻlqin):** Yerning gʻadir-budurligi va tuproq namligiga oʻta sezgir. Suv yuzasi silliq boʻlgani uchun toʻlqin aks etib ketadi va radarga qaytmaydi (juda past: −15 dB dan past). Bino va metallar esa nurni kuchli qaytaradi (−8 dB dan yuqori).
- **SAR VH (Vertikal joʻnatilib, gorizontal qaytgan toʻlqin):** Nurning qutblanishi oʻzgarishi (hajmiy tarqalish) faqat shox-shabbali daraxtlarda va qalin oʻsimliklarda yuz beradi.
- **VH − VV (Polarimetrik farq):** Oʻsimliklarning strukturaviy tuzilishi va qalinligini aniqlaydi.
- **RVI (Radar Vegetation Index — Radar Oʻsimlik Indeksi):** Radarga asoslangan oʻsimlik indeksi. 4 × VH / (VV + VH) formulasi bilan oʻlchanadi. U optik indekslar kabi bulutga bogʻliq emas.
- **SAR Suv Niqobi:** VV signali −15 dB dan past boʻlgan barcha silliq yuzalarni aniqlovchi qatlam.

### 4.4. Relyef va Topografik Koʻrsatkichlar (Copernicus DEM)

Relyef tahlili 30 metrlik raqamli balandlik modeli ustida loyihada noldan yozilgan matematik differensial formulalar orqali hisoblanadi:

- **Balandlik (Elevation):** Dengiz sathidan mutlaq balandlik (metrlarda).
- **Nishablik (Slope):** Xalqaro eʼtirof etilgan Xorn (Horn) usuli boʻyicha relyef balandligining gorizontal va vertikal yoʻnalishdagi hosilalari orqali har bir pikselning nishablik burchagi (0° dan 90° gacha) hisoblanadi.
- **Aspekt (Aspect — Yon Bagʻir Yoʻnalishi):** Nishablikning dunyo tomonlariga (shimol, sharq, janub, gʻarb) qaraganlik burchagi (0° dan 360° gacha). Bu quyosh nuri tushishi va qor/namlik erishini tushunish uchun muhim.
- **Hillshade (Relyefning 3D Soyasi):** Quyosh osmonda 45° balandlikda va shimoli-gʻarbda (315°) turgan deb hisoblanib, yer relyefining tabiiy 3D soyalari hosil qilinadi.
- **TRI (Terrain Ruggedness Index — Relyefning Gʻadir-budurlik Indeksi):** Markaziy piksel bilan uning 8 ta qoʻshnisi orasidagi balandlik farqlari kvadratlarining oʻrtacha ildizi. Relyefning qanchalik toshloq, qoyali yoki notekis ekanini koʻrsatadi.
- **TPI (Topographic Position Index — Topografik Joylashuv Indeksi):** Piksel balandligidan uning atrofidagi 5x5 maydonning oʻrtacha balandligi ayiriladi. Musbat qiymat — tepalik yoki qir, manfiy qiymat — vodiy yoki botiqlik.
- **Botiq Pastqamliklar (Depressions):** TPI koʻrsatkichi −1 metrdan past va nishabligi 3 darajadan kichik boʻlgan botiq joylar. Bu yogʻin yoqqanda suv toʻplanib, koʻlmak yoki botqoq hosil boʻladigan eng xavfli nuqtalardir.

### 4.5. Termal Koʻrsatkichlar (Landsat 8/9)

- **Yer Sathi Harorati (LST — Land Surface Temperature):** Landsat infraqizil termal sensori (ST_B10) nurlanishidan Plank qonuni va atmosferani tozalash koeffitsiyentlari orqali yer sirtining haqiqiy fizik harorati Selsiy shkalasida (°C) hisoblanadi. Bu oddiy havo harorati emas, balki tuproq yoki asfaltning qizish darajasidir.
- **Landsat NDVI:** Landsat sunʼiy yoʻldoshining qizil va infraqizil kanallari orqali hisoblangan oʻsimlik indeksi. U Sentinel-2 ning NDVI koʻrsatkichi bilan solishtirilib, ikki mustaqil kosmik apparat natijalari oʻzaro tekshiriladi (kross-tekshiruv).

### 4.6. Tuproq Namligi (SMAP)

- **sm_surface (Ustki Tuproq Namligi):** Tuproqning eng yuqori 0–5 santimetrlik qatlamidagi namlik hajmi (kub metr tuproqdagi suv ulushi, m³/m³).
- **sm_rootzone (Ildiz Qatlami Namligi):** Ekin ildizlari joylashgan 1 metrgacha chuqurlikdagi namlik zaxirasi.
- **Tuproq Namligi Trendi:** Oxirgi kunlar davomida namlik koʻpayib boryaptimi yoki bugʻlanib quryaptimi — eng kichik kvadratlar usuli orqali kunlik oʻzgarish tezligi (qiyalik) hisoblanadi.

---

## 5. Yer Qoplamini 10 Toifaga Ajratish (Klassifikatsiya Algoritmi)

Yer qoplamini aniqlash — bu tayyor tashqi qatlam emas, balki loyiha doirasida `backend/app/analysis/landcover.py` modulida **maxsus noldan yozilgan koʻp manbali algoritm**dir.

U optik indekslar, radar toʻlqinlari, relyef va tuproq namligini bitta mantiqiy zanjirga bogʻlaydi. Har bir 10 metrli piksel qatʼiy ustuvorlik iyerarxiyasi boʻyicha tekshiriladi:

```
[Optik nurlar] + [SAR Radar] + [DEM Relyef] + [SMAP Namlik]
                       │
                       ▼
           Ustuvorlik boʻyicha qoidalar:
 1. Ochiq tuproq   ───> (BSI > 0 va NDVI < 0.15)
 2. Siyrak oʻsimlik───> (0.15 ≤ NDVI < 0.3)
 3. Ekin / dala    ───> (0.3 ≤ NDVI ≤ 0.6, past tekstura)
 4. Daraxtzor      ───> (NDVI > 0.6 + yuqori tekstura yoki VH > -17 dB)
 5. Botqoqlik      ───> (NDVI 0.1–0.5 + 5 ta dalildan ≥ 3 tasi: NDWI, NDMI, pastqamlik, past VV, SMAP)
 6. Imorat         ───> (NDBI > 0, NDVI < 0.2, kuchli radar VV > -8 dB yoki yuqori tekstura)
 7. Kuygan hudud   ───> (NBR < 0.1 va oldingi sanaga nisbatan ΔNBR < -0.27)
 8. Suv            ───> (MNDWI > 0.1 yoki NDWI > 0.2 + radar tasdigʻi)
 9. Yoʻl (ehtimoliy) ─> (Morfologik xos qiymatlar: choʻzilganlik ≥ 4 va ingichka chiziq)
10. Koʻprik (ehtimoliy)> (Suv ustidan kesib oʻtgan 30 metrli yoʻl piksellari)
 0. Nomaʼlum/bulut ───> (Niqoblangan yoki oʻlchovsiz piksellar)
                       │
                       ▼
         Ishonchlilik koeffitsiyenti (0.0 – 1.0)
         + Sentinel-2 SCL bilan kross-nazorat
```

### Har bir toifaning batafsil tavsifi:

1. **Ochiq tuproq (Bare soil — 6-kod):** Yalangʻoch tuproq indeksi `BSI > 0` va oʻsimlik indeksi `NDVI < 0.15` boʻlgan joylar. Shudgor qilingan yerlar, qum va toshloqlar.
2. **Siyrak oʻsimlik (Sparse vegetation — 5-kod):** `0.15 ≤ NDVI < 0.3` oraligʻi. Choʻl oʻtlari, siyrak adir va dasht oʻsimliklari.
3. **Ekin / dala (Cropland — 4-kod):** `0.3 ≤ NDVI ≤ 0.6` oraligʻi. Oʻrtacha va tekis teksturali parvarishlangan ekin maydonlari.
4. **Daraxtzor (Forest — 3-kod):** Yashillik indeksi `NDVI > 0.6` boʻlishi shart, lekin faqat yashillik yetarli emas: daraxtlar qalinligini tasdiqlash uchun tasvir teksturasi gʻadir-budir boʻlishi yoki Sentinel-1 radarida shox-shabbalarning hajmiy tarqalishi (`VH > -17 dB`) boʻlishi kerak. Agar oʻta yashil boʻlib, sirt tekis boʻlsa — u daraxtzor emas, zich ekin deb olinadi.
5. **Botqoqlik (Swamp — 2-kod):** Oʻsimlik indeksi `0.1 ≤ NDVI ≤ 0.5` oraligʻida boʻlib, **5 ta mustaqil fizik dalildan kamida 3 tasi** mos kelishi shart:
   - Suv indeksi `NDWI > -0.1`;
   - Barg namligi `NDMI > 0.0`;
   - Relyefda botiq pastqamlik mavjudligi;
   - Radar toʻlqinlarining past qaytishi (`VV < -12 dB` — nam tuproq effekti);
   - SMAP orqali oʻlchangan yuqori tuproq namligi (`> 0.30 m³/m³`).
6. **Imorat (Built-up — 7-kod):** Shaharsozlik indeksi `NDBI > 0`, oʻsimlik deyarli yoʻq `NDVI < 0.2` va oʻta kuchli radar qaytishi (`VV > -8 dB` — metall va beton burchaklarning nurni qaytarish effekti). Agar radar boʻlmasa, yuqori fazoviy tekstura talab qilinadi.
7. **Kuygan hudud (Burnt area — 10-kod):** Yongʻin indeksi `NBR < 0.1` va oldingi kuzatuv sanasiga nisbatan indeks keskin tushib ketgan (`ΔNBR < -0.27`, xalqaro USGS standarti).
8. **Suv (Water — 1-kod):** Spektral suv indeksi `MNDWI > 0.1` yoki `NDWI > 0.2`. Agar radar ham suvning silliqligini tasdiqlasa (`VV < -15 dB`), ishonchlilik 100% deb olinadi.
9. **Yoʻl (ehtimoliy) (Roads — 8-kod):** Imorat yoki ochiq tuproq piksellari geometrik tahlil qilinadi: tutashgan piksellar kovariatsiya matritsasining xos qiymatlari (eigenvalues) hisoblanadi. Agar obʼyekt choʻzilgan (uzunligi kengligidan kamida 4 baravar katta) va ingichka chiziq boʻlsa — bu yoʻl deb belgilanadi.
10. **Koʻprik (ehtimoliy) (Bridges — 9-kod):** Yoʻl piksellarining suv bilan kesishuvi tekshiriladi: agar yoʻl suvga tegib turgan boʻlsa va uning ikki qarama-qarshi tomonida 30 metr masofada suv boʻlsa — bu suv ustidan oʻtgan koʻprik deb belgilanadi.
0. **Nomaʼlum / bulut (0-kod):** Qalin bulutlar yoki oʻlchovsiz joylar.

### Ishonchlilik Darajasi (Confidence Score)
Har bir pikselga 0 dan 1 gacha ishonch bali beriladi. Shuningdek, Sentinel-2 ning ichki SCL qatlami bilan solishtiriladi: agar bizning algoritm xulosasi SCL bilan zid kelsa (masalan, biz suv dedik, SCL oʻsimlik dedi), ishonchlilik bali 0.25 ga pasaytiriladi.

---

## 6. Dinamika, Ob-havo Taʼsiri va Sifat Nazorati

### 6.1. Oʻzgarishlarni Aniqlash (Change Detection)
- **ΔNDVI, ΔNDWI, ΔNDMI, ΔNBR:** Ketma-ket olingan haqiqiy kuzatuv sanalari orasidagi farq. Oʻsimliklarning oʻsishi (musbat) yoki qurishi (manfiy), suv sathi oʻzgarishi aniq koʻrinadi.
- **ΔVV:** Radarning vertikal toʻlqini oʻzgarishi — tuproqning namlanishi yoki qurishini koʻrsatadi.
- **Sinflar almashinuv matritsasi (Transitions):** Har bir yer toifasi necha gektarga oʻzgargani (masalan, 15 gektar ekin maydoni oʻrilib, ochiq tuproqqa aylangani) aniq hisoblanadi.

### 6.2. Ob-havo Taʼsiri Xulosalari (Agro-meteorologik Qoidalar)
Tizim raqamlar va sanalar bilan asoslangan 7 ta qatʼiy qoidaviy xulosa chiqaradi:
1. *Oʻtgan yogʻinlar va namlik:* Yogʻgan yomgʻir miqdori (mm) SMAP tuproq namligi va radar signalining oʻzgarishi bilan solishtiriladi.
2. *Harorat taqqoslovi:* Landsat oʻlchagan yer sathi harorati (LST) oʻsha paytdagi havo harorati bilan taqqoslanadi.
3. *Oʻsimliklar va ob-havo:* NDVI oʻzgarishi shu davrdagi issiqlik yoki qurgʻoqchilik bilan tahlil qilinadi.
4. *Botqoqlanish xavfi:* Kelgusi kunlarda prognoz yogʻini 15 mm dan oshsa va maydonda botiq pastqamliklar boʻlsa — botqoqlanish va suv bosish xavfi haqida ogohlantirish beriladi.
5. *Kuchli yomgʻir xavfi:* Kunlik prognoz 20 mm dan oshsa, sel va kuchli yogʻin xavfi belgilanadi.
6. *Qorasovuq va jazirama:* Havo harorati 0 °C dan tushsa — qorasovuq; 38 °C dan oshsa — jazirama xavfi qayd etiladi.
7. *Shamol xavfi:* Shamol tezligi 12 m/s dan oshsa, kuchli shamol xavfi deb baholanadi.

### 6.3. Maʼlumot Sifatini Nazorat Qilish
Har bir qatlam va har bir sana uchun yaroqli piksellar ulushi (`valid_pct`) va bulut bilan toʻsilgan ulush (`cloud_masked_pct`) oʻlchanadi. Agar yaroqli piksellar 30% dan kam boʻlsa — "past ishonchlilik", 60% dan ortigʻi bulut boʻlsa — "yuqori bulutlilik" belgisi qoʻyiladi.

---

## 7. "Rekognossirovka" Tugmasi Bosilganda Nimalar Sodir Boʻladi? (10 Bosqichli Quvur)

Foydalanuvchi xaritada hududni chizib, tugmani bosganda serverda 10 ta ketma-ket va uzluksiz bosqichdan iborat tahlil quvuri (Pipeline) ishga tushadi:

- **0-bosqich (Tekshiruv):** 100 km² chegarasi, geometriya toʻgʻriligi va bir vaqtda bitta ish qoidasi tekshiriladi.
- **1-2-bosqichlar (Toʻr):** 10 metrlik katakchalar toʻri (Grid) tortilib, har bir pikselning haqiqiy yer maydoni hisoblanadi.
- **3-bosqich (Qidiruv):** Oxirgi kunlardagi barcha Sentinel-2, Sentinel-1, Landsat suratlari topiladi.
- **4-bosqich (Barmoq izi):** 32 baytli kriptografik kod hisoblanadi. Yangi surat boʻlmasa, mavjud natija bir zumda ochiladi.
- **5-bosqich (Yuklash):** 512x512 pikselli boʻlaklar bilan spektral kanallar yuklanadi. Zarur boʻlsa, zaxira GEE loyihasiga oʻtiladi.
- **6-bosqich (Ob-havo):** ERA5-Land, GFS va CHIRPS dan oʻtgan va kelgusi ob-havo yigʻiladi.
- **7-bosqich (Tahlil):** 4 va 5-boʻlimlarda tasvirlangan barcha matematik formulalar, indekslar, relyef, yer qoplami va ob-havo taʼsirlari hisoblanadi.
- **8-bosqich (Render):** Xaritaga tushadigan shaffof PNG rasmlar va rangli kompozitlar chiziladi.
- **9-bosqich (Saqlash):** Barcha natijalar `summary.json` va maʼlumotlar bazasida doimiy saqlanadi.
- **10-bosqich (AI Hisoboti):** Katta til modeli (LLM) faqat shu hisoblangan sonlar asosida 7 boʻlimli professional tahliliy hisobot tuzadi.

---

## 8. Foydalanuvchi Interfeysi va Qoʻshimcha Imkoniyatlar

- **2D Xarita:** Esri World Imagery fonida barcha qatlamlarni shaffoflik bilan ustma-ust koʻrish, xarita ustiga bosib 10 metrlik pikselning barcha parametrlarini koʻrish.
- **3D Relyef (Three.js):** Copernicus DEM yordamida maydonni atrofdagi 1.5–40 km tabiiy landshafti bilan birga 360° aylantirib, balandlikni 1x–10x choʻzib koʻrish.
- **Vaqt Slayderi:** Faqat haqiqiy kuzatuv sanalari boʻyicha silliq oʻtish.
- **Maydon Chati:** Faqat ushbu maydon natijalari boʻyicha savollarga javob beradigan mutaxassis AI yordamchi.
- **ML / CV Ulanish Nuqtasi:** Kelajakda klassik mashinali oʻrganish (Random Forest, SVM) yoki chuqur neyron tarmoqlar (U-Net) modellarini dastur kodini oʻzgartirmasdan ulab qoʻyish arxitekturasi.
- **Tizim Nazorati:** Har bir API chaqiruvi, ketgan vaqt, baytlar va xarajatlar JSONL jurnallarida qayd etiladi. Muvaffaqiyatli maydonlar doimiy saqlanadi, bekor qilinganlari esa 24 soatda tozalanadi.

---

## 9. Xulosa

ZaminTahlil v2 — sunʼiy yoʻldosh maʼlumotlari, geofizik tahlillar va zamonaviy sunʼiy intellektni bitta nuqtada birlashtirgan, har qanday sunʼiy uydirmalardan holi, aniq va ishonchli qarorlar qabul qilishga moʻljallangan professional fazoviy tahlil platformasidir.
