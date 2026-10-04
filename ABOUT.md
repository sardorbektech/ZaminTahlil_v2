# ABOUT.md — ZaminTahlil v2 Tizimining Toʻliq Texnik va Mantiqiy Tavsifi

ZaminTahlil — foydalanuvchi xaritada tanlagan istalgan yer maydoni (toʻgʻri toʻrtburchak yoki erkin koʻpburchak shaklida, 100 kvadrat kilometrgacha) boʻyicha kompleks rekognossirovka (atroflicha fazoviy razvedka va tahlil) oʻtkazuvchi dasturiy majmuadir.

Tizim Google Earth Engine (GEE) platformasi orqali Yerni masofadan zondlovchi yetakchi sunʼiy yoʻldoshlar (Sentinel-2, Sentinel-1, Landsat 8/9, Copernicus DEM, SMAP) hamda global ob-havo xizmatlarining (ERA5-Land, GFS, CHIRPS) maʼlumotlarini avtomatik yuklab oladi. Yuklangan xom maʼlumotlar sof matematik va fizik formulalar yordamida tahlil qilinadi: oʻsimlik qoplami, namlik, suv havzalari, relyef nishabligi, yer sathi harorati, sunʼiy inshootlar va yer turlari aniqlanadi. Yakunda katta til modeli (LLM) barcha raqamli natijalarni jamlab, mutaxassis darajasidagi batafsil oʻzbekcha tahliliy hisobot tuzib beradi hamda maydon boʻyicha savol-javob chatini taqdim etadi.

Ushbu hujjatda loyihaning arxitekturasi, ishlash tamoyillari va unda kechadigan har bir jarayon oddiy va tushunarli tilda, kod parchalarisiz toʻliq yoritilgan.

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

## 4. "Rekognossirovka" Tugmasi Bosilganda Nimalar Sodir Boʻladi? (10 Bosqichli Quvur)

Foydalanuvchi xaritada hududni chizib, tugmani bosganda serverda 10 ta ketma-ket va uzluksiz bosqichdan iborat tahlil quvuri (Pipeline) ishga tushadi. Brauzer ekranida jarayon foizlar va oʻzbekcha tushunarli xabarlar bilan jonli koʻrinib turadi.

### 0-bosqich: Dastlabki Tekshiruvlar va Xavfsizlik
- Foydalanuvchi autentifikatsiyasi tekshiriladi.
- Serverda boshqa tahlil ketmayotganiga ishonch hosil qilinadi (agar boshqa ish ketsa, 409 bandlik xatosi beriladi).
- Tanlangan hudud koʻpburchagi matematik tekshiriladi: chiziqlari oʻzaro kesishmasligi, nuqtalari toʻgʻri ulanishi va umumiy maydoni 100 km² dan oshmasligi shart.
- Google Earth Engine xizmatiga ulanish kalitlari borligi tekshiriladi va tahlilga start beriladi.

### 1 va 2-bosqichlar: Koordinatalar Toʻri (Grid) va Maydonni Piksellarga Ajratish
- Hudud butun dunyo boʻylab qabul qilingan xarita proyeksiyasiga keltiriladi.
- Maydon 10 metrlik teng katakchalarga (piksellarga) boʻlinadi.
- Shunday qilib, xarita ustiga koʻrinmas toʻr tortiladi. Hudud ichiga tushgan har bir 10x10 metrli yer boʻlagi oʻzining aniq katakchasiga ega boʻladi. Har bir katakchaning haqiqiy yer yuzidagi maydoni sfera qonuniyatlari asosida gektar hisobida aniqlanadi.

### 3-bosqich: Sunʼiy Yoʻldosh Kadrlari Qidiruvi (Discovery)
- Tizim bir necha soniya ichida Google Earth Engine arxiviga soʻrov yuboradi.
- Tanlangan maydon ustidan oxirgi kunlar (sozlamaga qarab 10–14 kun) ichida uchib oʻtgan barcha Sentinel-2, Sentinel-1 va Landsat kadrlari roʻyxati, ularning vaqti va bulutlilik darajasi aniqlanadi.
- Bir kunda bir nechta kadr olingan boʻlsa, ular bitta kunlik kuzatuv mozaikasiga birlashtiriladi.

### 4-bosqich: Raqamli Barmoq Izi va Takroriy Ishdan Himoya (Fingerprint)
- Tanlangan koordinatalar, topilgan kadrlar roʻyxati va foydalanuvchi ID raqamidan yagona 32 baytli kriptografik kod — "Barmoq izi" hisoblanadi.
- Agar foydalanuvchi xuddi shu hududni avval tahlil qilgan boʻlsa va oʻtgan vaqt ichida fazodan hech qanday yangi surat tushmagan boʻlsa, tizim internetni va server quvvatini behuda sarflamaydi. U darhol: *"Yangi sunʼiy yoʻldosh maʼlumoti yoʻq"* deb xabar beradi va mavjud tayyor tahlilni bir lahzada ochib beradi.
- Yangi kadrlar paydo boʻlgan boʻlsa, tahlil keyingi bosqichga oʻtadi.

### 5-bosqich: Maʼlumotlarni Boʻlib-boʻlib Yuklab Olish (Download)
- Sunʼiy yoʻldosh maʼlumotlari toʻgʻridan-toʻgʻri raqamli matritsalar shaklida yuklanadi.
- Katta maydonlar xotirada qotib qolmasligi uchun 512x512 pikselli boʻlaklarga (plitkalarga) ajratilib, parallel ravishda olinadi.
- Har bir spektral nur kanali (koʻk, yashil, qizil, yaqin infraqizil, qisqa toʻlqinli infraqizil, radar toʻlqinlari va relyef balandligi) alohida yuklanadi.
- **Zaxira loyihaga avtomatik oʻtish (Failover):** Agar asosiy Google Earth Engine hisobida soʻrovlar limiti tugasa yoki xatolik yuz bersa, tizim toʻxtab qolmaydi. U bir soniyada ikkinchi zaxira hisobga ulanadi va ekranda *"Zaxira GEE loyihasiga oʻtildi"* deb bildirishnoma chiqarib, ishini davom ettiradi.

### 6-bosqich: Ob-havo Maʼlumotlarini Toʻplash
- Hudud boʻyicha oʻtgan 10–14 kunlik soatbay harorat, namlik, shamol va yogʻin maʼlumotlari yigʻiladi.
- Boʻshliqlar boʻlsa, eng yangi tahlillar bilan toʻldiriladi.
- Kelgusi kunlar uchun ob-havo prognozi olinadi. Har bir koʻrsatkich oʻrtacha, eng past va eng yuqori darajalari bilan belgilanadi.

### 7-bosqich: Chuqur Matematik va Fazoviy Tahlil (Sof NumPy)
Bu bosqichda barcha piksellar boʻyicha hisoblashlar amalga oshiriladi:
- **Bulutlarni tozalash:** Sunʼiy yoʻldoshning bulut va soya niqoblari orqali bulut qoplagan piksellar ajratib olinadi, ular tahlilga xalaqit bermasligi uchun chetlatiladi.
- **Optik indekslar hisobi:**
  - *NDVI va EVI:* Oʻsimliklarning yashillik va zichlik darajasi.
  - *NDRE:* Oʻsimliklarning xlorofill miqdori va sogʻlomlik holati.
  - *NDWI va MNDWI:* Ochiq suv havzalari va namlik toʻplangan joylar.
  - *NDMI:* Barglar ichidagi suv zaxirasi.
  - *NDBI:* Shaharsozlik, bino va inshootlar zichligi.
  - *BSI:* Ochiq, oʻsimliksiz yalangʻoch tuproq maydonlari.
  - *NBR:* Yongʻin koʻrgan yoki kuygan maydonlar.
- **Radar (SAR) tahlili:** Radar toʻlqinlaridagi shovqinlar maxsus 5x5 Li filtri orqali tekislanadi. Suvning nurni qaytarmaslik xususiyati orqali suv havzalari aniqlanadi.
- **Relyef tahlili:** Balandlik matritsasidan qiyaliklar (nishablik darajasi), quyoshga qaraganlik tomoni (ekspozitsiya), relying relyef gʻadir-budirligi hamda suv toʻplanib qolishi mumkin boʻlgan botiq pastqamliklar aniqlanadi.
- **Yer sathi harorati:** Landsat orqali yerning haqiqiy issiqlik darajasi (°C) chiqariladi.
- **Yer qoplamini 10 toifaga ajratish (Klassifikatsiya):** Har bir 10 metrlik piksel qatʼiy mantiqiy qoidalar asosida quyidagi toifalardan biriga ajratiladi:
  1. *Suv* (daryo, koʻl, kanal)
  2. *Botqoqlik* (nam tuproq, qamishzor, pastqam joylar)
  3. *Daraxtzor* (oʻrmon, bogʻ, qalin daraxtlar)
  4. *Ekin / dala* (qishloq xoʻjaligi maydonlari)
  5. *Siyrak oʻsimlik* (yaylov, dasht oʻtlari)
  6. *Ochiq tuproq* (shudgor, qumloq, toshloq)
  7. *Imorat* (turar joylar, sanoat binolari)
  8. *Yoʻl (ehtimoliy)* (choʻzilgan va davomiy chiziqli qattiq qoplamalar)
  9. *Koʻprik (ehtimoliy)* (suv ustidan oʻtgan yoʻl yoki inshoot piksellari)
  10. *Kuygan hudud* (oʻsimliklari yonib ketgan yerlar)
  0. *Nomaʼlum / bulut* (koʻrinmagan joylar)
- **Oʻzgarishlarni aniqlash:** Bir necha kun farq bilan olingan suratlar taqqoslanadi: oʻsimliklar qayerda koʻpaydi yoki quridi, suv sathi qayerda koʻtarildi, ekinlar oʻrildi yoki yoʻqmi — hammasi foizlarda hisoblanadi.
- **Maʼlumot sifatini baholash:** Har bir qatlam va har bir sana uchun yaroqli piksellar foizi hisoblanadi. Agar 30% dan kam joy koʻringan boʻlsa, "past ishonchlilik" belgisi qoʻyiladi.
- **Ob-havo taʼsirini baholash:** Oʻtgan yomgʻirlar tuproq namligi va radar signalini qanchalik oshirgani, jazirama harorat ekinlarga qanday taʼsir qilgani va kutilayotgan kuchli yogʻinlar pastqam joylarda suv toshishi xavfini tugʻdirishi aniqlanadi.

### 8-bosqich: Shaffof Xarita Qatlamlarini Chizish (Render)
- Hisoblangan raqamlar matritsasidan xaritaga toʻgʻridan-toʻgʻri tushadigan shaffof PNG rasmlar tayyorlanadi.
- Har bir qatlam uchun maxsus ranglar palitrasi qoʻllanadi (masalan, NDVI uchun qizil-sariq-yashil shkala, balandlik uchun topografik ranglar, suv uchun moviy rang).
- Maydondan tashqaridagi barcha piksellar toʻliq shaffof qilinadi.
- Tabiiy rangdagi (RGB) va sunʼiy infraqizil rangdagi kompozit suratlari generatsiya qilinadi.

### 9-bosqich: Natijalarni Xavfsiz Saqlash (Persist)
- Barcha hisoblangan raqamlar, gektarlar, jadvallar, ob-havo koʻrsatkichlari va qatlamlar metamaʼlumotlari `summary.json` yagona fayliga jamlanadi.
- Maʼlumotlar bazasiga barcha kadrlar, qatlamlar va statistik qatorlar yoziladi.
- Tahlil maqomi "Yakunlandi" (COMPLETED) holatiga oʻtkaziladi.

### 10-bosqich: Sunʼiy Intellekt (AI) Hisoboti
- Katta til modeliga (standart: eng yangi OpenAI modeli) maydonning barcha raqamli koʻrsatkichlari ixcham shaklda uzatiladi.
- AI ga qatʼiy koʻrsatma beriladi: *faqat berilgan sonlarga tayan, bitta ham fakt yoki joy nomini toʻqima, sanalarni Toshkent vaqti bilan yoz, noaniq narsalarni past ishonchli deb taʼkidla*.
- Model aynan 7 ta majburiy boʻlimdan iborat tahliliy hisobot yozadi:
  1. *Umumiy maʼlumot*
  2. *Relyef*
  3. *Yer qoplami*
  4. *Oʻzgarishlar*
  5. *Ob-havo va taʼsiri*
  6. *Prognoz va xavflar*
  7. *Maʼlumot sifati va cheklovlar*
- Tizim AI javobini tekshiradi: agar birorta boʻlim tushib qolgan boʻlsa, xatoni tuzatish soʻrovi yuboriladi. Hisobot tayyor boʻlgach, u ekranda koʻrsatiladi va uni yuklab olish mumkin boʻladi. (Agar AI xizmatida vaqtinchalik xatolik boʻlsa ham, xarita va tahlillar bekor boʻlmaydi, hisobotni keyinroq qayta generatsiya qilish mumkin).

---

## 5. Natijalarni Koʻrish va Interfeys Imkoniyatlari

Foydalanuvchi interfeysi zamonaviy geoinformatsion tizimlar kabi qulay va tezkor ishlaydi:

### 2D Xarita
- Asosiy fon sifatida Esri World Imagery yuqori sifatli kosmik xaritasi xizmat qiladi.
- Istalgan tahlil qatlamini (oʻsimliklar, suv, harorat, yer turlari, relyef) xaritaga qoʻshish, uning shaffofligini oʻzgartirish va bir nechta qatlamni ustma-ust koʻrish mumkin.
- Xaritada yer qoplamining nomlarini (masalan, "Dala", "Suv", "Bino") yozuvlar sifatida yoqish mumkin.
- **Piksel ustiga bosish:** Xaritaning istalgan nuqtasiga bosilganda, oʻsha 10 metrlik nuqtadagi barcha maʼlumotlar (dengiz sathidan balandligi, harorati, qaysi kunda NDVI nechchi boʻlgani, yer turi va ishonchliligi) alohida oynada ochiladi.
- **Kanal kompozitori:** Sentinel-2 ning turli nurlar diapazonlarini (qizil, yashil, koʻk, infraqizil) oʻzaro aralashtirib, maxsus ilmiy rangli suratlarni yaratish mumkin.

### 3D Relyef va Atrof-muhit Modeli
- Three.js texnologiyasi asosida maydonning toʻliq uch oʻlchamli (3D) modeli chiziladi.
- Model asosi sifatida Copernicus DEM balandliklari olinadi.
- **Atrof-muhit bilan koʻrish:** Tahlil qilingan maydon havoda osilib qolmasligi uchun, tizim uning atrofidagi 1.5–40 kilometrlik qoʻshni relyefni ham yuklaydi va maydonni oʻzining tabiiy togʻ-adirlari yoki vodiysi bagʻrida koʻrsatadi.
- 3D yuzaga 2D xaritada tanlangan barcha qatlamlar va kosmik fotosuratlar xuddi tekstura kabi kiydiriladi.
- Relyef balandligini yaqqolroq koʻrish uchun vertikal choʻzish (1x dan 10x gacha) boshqaruvi mavjud.
- Sichqoncha yordamida hududni 360 daraja aylantirish, yaqinlashtirish va har tomondan koʻzdan kechirish mumkin.

### Vaqt Slayderi (Kuzatuv Sanalari)
- Slayderda faqat sunʼiy yoʻldoshlar haqiqatda suratga olgan real sanalar joylashgan.
- Slayderni surish orqali turli sanalardagi holatni silliq koʻrish mumkin: eski sana ustiga yangi sana asta-sekin shaffof tarzda oʻtib boradi.
- Sunʼiy yoki toʻqib chiqarilgan oraliq kadrlar yoʻq — har bir holat fazodan olingan haqiqiy hujjatdir.

### Maydon Boʻyicha AI Suhbat (Chat)
- Interfeysda sunʼiy intellekt bilan muloqot qilish oynasi mavjud.
- Bu oddiy umumiy chat emas: model faqat va faqat tanlangan maydonning oʻlchangan koʻrsatkichlari boʻyicha mutaxassis sifatida javob beradi.
- Masalan: *"Bu maydonda ekin ekish uchun namlik yetarlimi?"*, *"Oxirgi haftada oʻsimliklar nega sargʻaygan?"* yoki *"Qayerda botqoqlanish xavfi bor?"* kabi savollarga raqamlar bilan asoslab javob beradi.
- Agar foydalanuvchi maydonga aloqador boʻlmagan mavzuda (sheʼr yozish, siyosat, umumiy suhbat) savol bersa, yordamchi qatʼiy ravishda: *"Men faqat shu maydon va uning tahlil natijalari haqidagi savollarga javob beraman"* deb rad etadi.

---

## 6. Mashinali Oʻrganish (ML) va Kompyuter Koʻrishi (CV) Modellarini Ulash

Loyiha arxitekturasi kelajakda qoidaviy tahlil oʻrniga yoki unga qoʻshimcha sifatida zamonaviy neyrotarmoqlar va sunʼiy intellekt modellarini ulash uchun maxsus tayyorlangan:

- **Piksel modellari (Classic ML):** Har bir pikselning spektral xususiyatlaridan foydalanib ishlaydigan modellar (Random Forest, Gradient Boosting, SVM). Ular qatlamlar roʻyxatiga yangi xaritalar qoʻshishi yoki asosiy yer qoplami klassifikatorining oʻrnini egallashi mumkin.
- **Tasvir modellari (Computer Vision):** Chuqur neyron tarmoqlar (U-Net, segmentatsiya modellari) butun hudud tasvirini tahlil qilib, obʼyektlarni (masalan, yoʻllar tarmogʻi, binolar konturi, dalalar chegaralari) aniqlay oladi.
- Yangi model qoʻshilganda dasturning boshqa qismlarini yoki interfeysni qayta yozish shart emas: tizim modelni avtomatik taniydi, natijalarini qatlamlar katalogiga joylaydi va foydalanuvchiga taqdim etadi.

---

## 7. Tizim Nazorati, Xarajatlar Jurnali va Xotirani Tozalash

- **Har bir chaqiruv hisobda:** Google Earth Engine va AI provayderlariga yuborilgan har bir soʻrov, ketgan vaqt (millisekundlarda), yuklangan baytlar hajmi, ishlatilgan tokenlar va narxi alohida JSONL jurnallarida qayd etiladi.
- **Nazorat paneli:** Foydalanuvchi "Nazorat" boʻlimida ushbu maydon tahlili uchun qancha resurs sarflanganini, qaysi xizmatlar qancha ishlaganini toʻliq koʻra oladi.
- **Avtomatik tozalash tartibi:** 
  - Muvaffaqiyatli tahlillar (saqlangan maydonlar) foydalanuvchi oʻzi oʻchirmaguncha saqlanadi.
  - Xatolik bilan toʻxtagan yoki yarim yoʻlda qolgan vaqtinchalik urinishlar 24 soatdan soʻng avtomatik oʻchiriladi.
  - API chaqiruvlari jurnallari 30 kun saqlanadi.
  - Tozalash jarayoni server yoqilganda va har 10 daqiqada fonda avtomatik ishlab turadi.

---

## 8. Xulosa

ZaminTahlil v2 — sunʼiy yoʻldosh maʼlumotlari, geofizik tahlillar va zamonaviy sunʼiy intellektni bitta nuqtada birlashtirgan, har qanday sunʼiy uydirmalardan holi, aniq va ishonchli qarorlar qabul qilishga moʻljallangan professional fazoviy tahlil platformasidir.
