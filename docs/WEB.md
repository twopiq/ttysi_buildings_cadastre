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
- Kirish kodi (`--pin`), telefon ekraniga qo'shish (PWA manifest).

Ishga tushirish (sinov uchun, ofis tarmog'ida):

```
pip install -r web/requirements.txt
python -m web.server --workspace "D:\TTYSI Binolar" --host 0.0.0.0 --pin 2468
```

Telefon shu Wi-Fi tarmog'ida bo'lsa: `http://<kompyuter-IP>:8000`.

> Muhim: desktop dasturda bino ochiq turgan paytda saytda o'sha binoni o'zgartirmang — dastur saqlaganda
> saytdagi o'zgarishlar ustidan yozib yuboradi. (2-bosqichda hal qilinadi.)

## Keyingi bosqichlar

**2. Ko'p foydalanuvchi va server ma'lumotlar bazasi**
- Foydalanuvchilar va rollar (admin / xodim / faqat ko'rish), parol bilan kirish, harakatlar jurnali.
- Ma'lumot: PostgreSQL (bino, etaj, xona, jihoz jadvallari) + kadastr rasmlari uchun fayl ombori (S3/MinIO).
  `.ttysi` — import/eksport formati bo'lib qoladi.
- Desktop dastur bilan sinxronlash: "Serverga yuklash / serverdan olish", versiya va to'qnashuvlarni hal qilish.

**3. Rasmdan avtomatik chizish saytda**
- Kadastr PDF/rasmini yuklash (telefon kamerasidan ham), perspektivani to'g'rilash, xonalarni va qo'lyozma
  belgilarni topish — `detection.py` va `marks.py` serverda (fon vazifasi sifatida) ishlaydi.

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
| `POST /api/login` | kirish kodi (agar berilgan bo'lsa) |
