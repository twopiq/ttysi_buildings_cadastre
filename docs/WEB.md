# Sayt versiyasi — reja va hozirgi holat

Maqsad: TTYSI Binolar kadastri **brauzerda** ham ishlasin — kompyuterda (katta ekran, sichqoncha) va
**telefonda** (bino ichida yurib, AT jihozlarini joyida belgilash). Desktop dastur yo'qolmaydi: ikkalasi
bitta ma'lumot formatidan (`.ttysi`) va bitta yadro koddan foydalanadi.

## Arxitektura

```
ttysi_cadastre/            umumiy yadro (Qt'siz — serverda ham ishlaydi)
  model.py                 Building / Floor / Room / Equipment, .ttysi fayl formati
  geometry.py, metrics.py  geometriya, devor qalinligi, belgi o'lchami, eshik/zina chiziqlari
  detection.py, marks.py   rasmdan xonalar va qo'lyozma AT belgilarini topish (OpenCV)
  report.py                Excel hisobot
  workspace.py             binolar papkasi: binolar va tashkilotlar ro'yxati
  plan_json.py             etaj chizmasi brauzer uchun (SVG chizishga tayyor ma'lumot)
  ui/, render.py, export.py  faqat desktop (PySide6)

web/
  server.py                FastAPI: API + sahifa
  static/                  sahifa: index.html, app.js, style.css (yig'ish/build talab qilmaydi)
```

`tests/test_web.py` yadro modullari PySide6'siz import qilinishini tekshiradi — bu chegarani buzmaslik kerak.

## 1-bosqich (tayyor, sinov uchun)

- Binolar ro'yxati tashkilotlar bo'yicha, qidiruv.
- Etaj chizmasi: xonalar, maydonlar, devorlar, eshiklar, zinalar, gumbazlar, AT belgilari; kadastr foni
  (yoqib/o'chirib). Telefonda barmoq bilan surish va ikki barmoq bilan kattalashtirish, kompyuterda g'ildirak.
- AT belgilari: turini tanlab chizmani bosish — qo'shiladi; belgini bosish — turi, holati (mavjud/kerak),
  izohi, o'chirish. "Keyingi ?" — tasdiqlanmagan belgilarni ketma-ket tasdiqlash. Kompyuterda 1–6 tugmalari.
- Excel hisobot: bino yoki butun tashkilot bo'yicha yuklab olish.
- O'zgarishlar darhol `.ttysi` faylga yoziladi (desktop dastur ochadi). Bir vaqtda ikki joyda o'zgartirilsa
  (ETag/If-Match), keyingisi rad etiladi va sahifa yangilanadi — ma'lumot yo'qolmaydi.
- Telefon ekraniga qo'shish (PWA manifest).

## 2-bosqich (qisman tayyor)

- **Foydalanuvchilar va rollar:** Ko'ruvchi (faqat ko'radi, hisobot oladi), Tahrirlovchi (AT belgilarini
  kiritadi), Administrator (hammasi + foydalanuvchilar). Parollar PBKDF2 xeshi bilan saqlanadi; parol
  o'zgarsa yoki foydalanuvchi o'chirilsa, uning ochiq sessiyalari darhol bekor bo'ladi.
  Birinchi administrator faqat server kompyuterining o'zida yaratiladi (`http://localhost:8000` →
  yuqori o'ngdagi ⚙ → "Administrator yaratish") yoki buyruq bilan:
  `python -m web.auth --workspace "D:\TTYSI Binolar" add admin --role admin`.
- **O'zgarishlar jurnali:** kim, qachon, qaysi bino/etajda qaysi belgini qo'shgan/o'zgartirgan/o'chirgan.
  Bino sahifasida — so'nggi o'zgarishlar, administratorda — to'liq jurnal.
- **Desktop dastur bilan birga ishlash:** dastur faylning saytda o'zgarganini o'zi sezadi (har 5 soniyada,
  oynaga qaytganda va saqlashdan oldin) va o'zgarishlarni qo'shib oladi — saytdagi belgilar endi
  yo'qolmaydi. Ikkala joyda bitta belgi turlicha o'zgartirilsa, dasturdagisi qoladi.
- Ma'lumotlar `<Binolar papkasi>/.ttysi-web/` da (users.json, journal.jsonl).
- Qolgani: PostgreSQL va fayl ombori (ko'p serverli o'rnatish uchun), desktopda serverga ulanish.

## 3-bosqich (tayyor): saytda yangi bino va etaj

- **+ Tashkilot** (administrator), **+ Bino** (tahrirlovchi) — bosh sahifada.
- **+ Etaj** — kadastr PDF, skaner yoki telefon rasmi (telefonda kamera bilan darhol suratga olish).
  PDF bo'lsa sahifani tanlaysiz, ko'rinishi chiqadi; nisbat (1:300 ...) bo'yicha masshtab hisoblanadi.
  Telefon rasmida qog'oz burchaklari topilsa, perspektiva o'zi to'g'rilanadi.
- Xonalar, eshiklar va qo'lyozma AT belgilari desktop dasturdagi bilan bir xil kod bilan serverda (fon
  vazifasi) aniqlanadi; jarayon holati sahifada ko'rinadi.
- Tayyor bo'lgach **tasdiqlash** o'zi boshlanadi: har bir «?» belgi uchun kadastr rasmidagi qo'lyozma bo'lagi
  ko'rsatiladi, turini bosasiz — keyingisiga o'tadi.

## Ishga tushirish

**Windows (eng oson):** `web\start_web.bat` ni ikki marta bosing (Python 3.12 o'rnatilgan bo'lishi kerak).
Binolar papkasi boshqa joyda bo'lsa: `web\start_web.bat "D:\TTYSI Binolar"`.

**Qo'lda:**
```
pip install -r web/requirements.txt
python -m web.server --workspace "D:\TTYSI Binolar" --host 0.0.0.0
```

**Server (Docker):**
```
docker build -f web/Dockerfile -t ttysi-web .
docker run -d -p 8000:8000 -v "/srv/TTYSI Binolar:/data" --name ttysi-web ttysi-web
docker exec -it ttysi-web python -m web.auth --workspace /data add admin --role admin
```

Telefon shu tarmoqda bo'lsa: `http://<kompyuter-IP>:8000`. Foydalanuvchilar yaratilmaguncha sayt
kirishsiz ochiq — tarmoqqa ochishdan oldin administrator yarating.

## Keyingi bosqichlar

**2. Server ma'lumotlar bazasi** (foydalanuvchilar, rollar va jurnal — tayyor, yuqoriga qarang)
- Ma'lumot: PostgreSQL (bino, etaj, xona, jihoz jadvallari) + kadastr rasmlari uchun fayl ombori (S3/MinIO).
  `.ttysi` — import/eksport formati bo'lib qoladi.
- Desktop dastur bilan sinxronlash: "Serverga yuklash / serverdan olish", versiya va to'qnashuvlarni hal qilish.

**4. To'liq tahrirlovchi**
- Xonalar, devorlar, eshiklar, zinalarni chizish va tuzatish (desktopdagi asboblar), bekor qilish/qaytarish.
- PDF/PNG/DXF eksport serverda.

**5. Oflayn ishlash (telefon)**
- Service worker: tanlangan binolar telefonga saqlanadi, internet yo'q joyda (yerto'la, chekka bino)
  belgilar kiritiladi va aloqa tiklanganda yuboriladi.

**6. Joylashtirish**
- Docker obraz, HTTPS (domen yoki institut ichki serveri), zaxira nusxalar.

## Texnik qarorlar

- Frontend hozircha yig'ishsiz oddiy JS (tez ishga tushadi, telefonda yengil). Tahrirlovchi kattalashganda
  TypeScript + Vite'ga o'tish rejalashtirilgan; API o'zgarmaydi.
- Chizma SVG: vektor, har qanday kattalashtirishda aniq; geometriya serverda desktop bilan bir xil hisoblanadi
  (`plan_json.py`), shuning uchun sayt va dastur chizmasi farq qilmaydi.
- Koordinatalar — etaj piksellari (`.ttysi` dagidek); metrga o'tkazish `scale_m_per_px` orqali.

## API (1-bosqich)

| So'rov | Vazifa |
|---|---|
| `GET /api/info` | versiya, jihoz turlari va ranglari, xona turlari |
| `GET /api/workspace` | tashkilotlar va binolar (qisqa ma'lumot) |
| `GET /api/building?id=` | bino va barcha etajlar chizmasi; `ETag` |
| `GET /api/floor-image?id=&floor=` | etajning kadastr rasmi |
| `POST /api/equipment?id=` | belgi qo'shish / o'zgartirish / o'chirish (`If-Match`) |
| `GET /api/report.xlsx?id=` yoki `?org=` | Excel hisobot |
| `POST /api/orgs`, `POST /api/buildings` | yangi tashkilot / bino |
| `POST /api/upload`, `GET /api/upload/preview` | kadastr faylini yuklash (PDF sahifalar soni, ko'rinish) |
| `POST /api/floors?id=`, `GET /api/jobs/{id}` | yuklangan fayldan etaj (fon vazifasi va uning holati) |
| `GET /api/mark-crop` | belgi atrofidagi kadastr rasmi bo'lagi (tasdiqlash uchun) |
| `GET /api/me`, `POST /api/login`, `POST /api/logout` | kim kirgan, kirish/chiqish |
| `POST /api/setup` | birinchi administrator (faqat server kompyuteridan) |
| `GET/POST/DELETE /api/users` | foydalanuvchilar (administrator) |
| `GET /api/journal?id=` | o'zgarishlar jurnali (bino bo'yicha; umumiy — administrator) |
