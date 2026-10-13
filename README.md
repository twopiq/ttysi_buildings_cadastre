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

### Qog'ozdagi qo'lyozma belgilar

Tekshiruv vaqtida qog'ozga turli shaklda yozilgan belgilar quyidagicha tasdiqlanadi:

| Qog'ozda | Tugma | Jihoz |
|---|---|---|
| Ser. | 1 | Serverxona |
| K.x. (kommutatsion) | 2 | Kommutatsion xona |
| K, K., Kam, кам, X | 3 | Kamera |
| W | 4 | Wi-Fi |
| S, A.S | 5 | Switch / Hub |
| T, t | 6 | Internet nuqtasi |
| K.S | 3 va 5 | bitta joyda Kamera + Switch (ikkita belgi) |

- `103-x` kabi yozuvlar — **xona raqami** (103-xona). U xonaning nomiga yoziladi.
- "Kompyuter xona" — jihoz emas, **xona turi**: o'ng tugma → Turi → Kompyuter xona.

## Ish tartibi

1. **Etaj → PDF / rasmdan yangi etaj qo'shish (Ctrl+I).**
   - **PDF:** sahifani tanlaysiz. Bitta sahifada bir nechta etaj bo'lsa, keraklisini sichqoncha bilan
     ramkaga olasiz. Shtampdagi **Nisbat**ni (masalan 1:300) kiritsangiz, masshtab avtomatik hisoblanadi
     va maydonlar m² da chiqadi. Bitta PDF'dan bir nechta etajni ketma-ket qo'shish mumkin.
   - **Telefon rasmi:** dastur qog'oz burchaklarini o'zi topadi va perspektivani to'g'rilaydi. Qizil
     nuqtalarni qo'lda ham surish mumkin. Masshtabni keyin "Masshtabni belgilash" orqali berasiz.
2. **Avtomatik chizish.** Dastur devorlarni topib, xonalar va koridorlarni ko'pburchak qilib chizadi
   va **raqamlaydi** (keyin qo'lda tuzatiladi). **Ko'k ruchka** izlarini esa `?` belgisi bilan AT
   nomzodi sifatida belgilaydi.
3. **Belgilarni tasdiqlash.** `N` tugmasi keyingi `?` belgiga o'tkazadi, `1`–`6` turini beradi, `Del`
   noto'g'ri belgini o'chiradi. Qora ruchkadagi belgilarni chap paneldan qo'lda qo'yasiz.
4. **Tuzatish:**
   - burchaklarni sudrash;
   - qirrani ikki marta bosib yangi burchak qo'shish;
   - `B` — xonani chiziq bilan bo'lish;
   - `Ctrl+M` — xonalarni birlashtirish;
   - `P` / `R` — yangi xona chizish;
   - o'ng tugma — xona turini tanlash (xona, koridor, kompyuter xona, zinapoya, hojatxona);
   - `D` — **eshik**: devorga bosasiz va u eng yaqin devorga yopishadi. Sudrab boshqa devorga
     ko'chirish mumkin. O'ng tugma menyusida: bir yoki ikki tabaqali, ochilish tomoni, sharnir tomoni,
     kengligi (0.8–1.8 m);
   - `Z` — **zina**: maydonini to'rtburchak qilib torting. Ichida pog'onalar va yo'nalish strelkasi
     chiziladi.
5. **Mavjud va kerak jihozlar.** Har bir jihozning holati bor:
   - **Mavjud** — chizmada to'liq rangli belgi;
   - **Kerak (o'rnatilishi rejada)** — oq fonli, punktir chegarali belgi.

   Holatni o'zgartirish usullari: jihozni tanlab `Ctrl+K`, o'ng tugma menyusi yoki xususiyatlar
   paneli. Asboblar panelidagi **"Kerak (reja)"** (`Q`) yoqilsa, yangi qo'yilgan jihozlar darhol
   "kerak" bo'ladi. Masalan: kompyuter xonasida internet yo'q bo'lsa, xona turini "Kompyuter xona"
   qilasiz va unga "kerak" holatidagi Switch qo'yasiz.
6. **Masshtab (Etaj menyusi).** Uzunligi ma'lum devorni belgilasangiz, maydonlar m² da chiqadi va DXF
   metrlarda saqlanadi.
7. **Fayl → Eksport:**
   - PNG / JPG va SVG;
   - PDF (joriy etaj yoki barcha etajlar);
   - DXF (AutoCAD; qatlamlar `XONA_*` va `AT_*`, jihozlar bloklar sifatida);
   - **Excel hisobot** — joriy bino yoki bir nechta bino (`.ttysi` fayllar) bo'yicha: etajlar
     kesimida mavjud jihozlar soni, har bir xonadagi jihozlar, jihozlarning to'liq ro'yxati va
     **"Kerak (reja)"** varag'i: qaysi bino, etaj va xonaga nima o'rnatish kerakligi.
   - DXF'da rejadagi jihozlar alohida `AT_<kod>_KERAK` qatlamida, punktir chiziq bilan chiqadi.
     Eshiklar `ESHIKLAR`, zina pog'onalari esa `ZINALAR` qatlamida bo'ladi.

Loyiha bitta `.ttysi` faylda saqlanadi: bino, barcha etajlar va kadastr rasmlari shu faylning ichida bo'ladi.

## Cheklovlar

- Qo'lyozma harflarni ("K.x.", "S" va boshqalar) mahalliy usul ishonchli o'qiy olmaydi. Shuning uchun
  dastur belgining **joyini** topadi, **turini** esa siz bitta tugma bilan tasdiqlaysiz.
- Qora ruchkadagi belgilarni bosma chizmadan rang bo'yicha ajratib bo'lmaydi. Sozlamalarda "qora
  yozuvlarni nomzod qilish" degan tajribaviy variant bor, lekin unga bosma raqamlar ham tushadi.
- Avtomatik chizma taxminiy natija beradi va uni albatta ko'zdan kechirish kerak. Haqiqiy kadastr
  hujjatlarida (PDF va telefon rasmlari) xonalarning taxminan 65–90% i to'g'ri ajraladi. Ba'zan bitta
  xona ikkiga bo'linadi yoki koridorga qo'shilib ketadi — `Ctrl+M` va `B` bilan tuzatiladi. Ramka
  chetiga tegib turgan xonalar tushib qolishi mumkin, shuning uchun etajni ramkaga biroz bo'sh joy
  qoldirib oling. Xonalar bir-biriga
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
