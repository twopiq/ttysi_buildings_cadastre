# TTYSI binolar kadastri — AT jihozlari xaritasi

Kadastr hujjatidagi etaj rejasining rasmidan (skaner yoki telefon rasmi) taxminiy elektron chizma
tayyorlaydigan Windows dasturi. Dastur AT jihozlarining joylashuvini belgilaydi, chizmani tahrirlash
imkonini beradi va tayyor etajni rasm yoki chizma ko'rinishida eksport qiladi.

Hamma ish kompyuterning o'zida bajariladi: internet ham, AI xizmati ham kerak emas.

## AT jihozlari belgilari

| Tugma | Belgi | Ma'nosi |
|---|---|---|
| 1 | Ser. | Serverxona |
| 2 | K.x. | Kommutatsion xona |
| 3 | K. | Kamera |
| 4 | W | Wi-Fi |
| 5 | S | Switch / Hub |
| 6 | T | Internet nuqtasi (tochka) |

## Ish tartibi

1. **Etaj → Rasmdan yangi etaj qo'shish (Ctrl+I).** Rasm telefonda olingan bo'lsa, dastur qog'oz
   burchaklarini o'zi topadi va perspektivani to'g'rilaydi. Qizil nuqtalarni qo'lda ham surish mumkin.
2. **Avtomatik chizish.** Dastur devorlarni topib, xonalar va koridorlarni ko'pburchak qilib chizadi.
   **Ko'k ruchka** izlarini esa `?` belgisi bilan AT nomzodi sifatida belgilaydi.
3. **Belgilarni tasdiqlash.** `N` tugmasi keyingi `?` belgiga o'tkazadi, `1`–`6` turini beradi, `Del`
   noto'g'ri belgini o'chiradi. Qora ruchkadagi belgilarni chap paneldan qo'lda qo'yasiz.
4. **Tuzatish:**
   - burchaklarni sudrash;
   - qirrani ikki marta bosib yangi burchak qo'shish;
   - `B` — xonani chiziq bilan bo'lish;
   - `Ctrl+M` — xonalarni birlashtirish;
   - `P` / `R` — yangi xona chizish;
   - o'ng tugma — xona turini tanlash (xona, koridor, zinapoya, hojatxona).
5. **Masshtab (Etaj menyusi).** Uzunligi ma'lum devorni belgilasangiz, maydonlar m² da chiqadi va DXF
   metrlarda saqlanadi.
6. **Fayl → Eksport:**
   - PNG / JPG va SVG;
   - PDF (joriy etaj yoki barcha etajlar);
   - DXF (AutoCAD; qatlamlar `XONA_*` va `AT_*`, jihozlar bloklar sifatida).

Loyiha bitta `.ttysi` faylda saqlanadi: bino, barcha etajlar va kadastr rasmlari shu faylning ichida bo'ladi.

## Cheklovlar

- Qo'lyozma harflarni ("K.x.", "S" va boshqalar) mahalliy usul ishonchli o'qiy olmaydi. Shuning uchun
  dastur belgining **joyini** topadi, **turini** esa siz bitta tugma bilan tasdiqlaysiz.
- Qora ruchkadagi belgilarni bosma chizmadan rang bo'yicha ajratib bo'lmaydi. Sozlamalarda "qora
  yozuvlarni nomzod qilish" degan tajribaviy variant bor, lekin unga bosma raqamlar ham tushadi.
- Avtomatik chizma taxminiy natija beradi va uni albatta ko'zdan kechirish kerak. Xonalar bir-biriga
  qo'shilib ketsa — "Eshik kengligi"ni oshiring. Ortiqcha mayda xonalar chiqsa — "Eng kichik xona"ni oshiring.

## O'rnatish

**Tayyor dastur.** GitHub → Actions → "Windows build" → `TTYSI_Kadastr_Windows.zip` faylini yuklab oling.
Arxivni oching va `TTYSI_Kadastr.exe` ni ishga tushiring.

**Manba koddan ishga tushirish:**

```
pip install -r requirements.txt
python run.py
```

**Testlar:**

```
pip install pytest
python -m pytest tests
```
