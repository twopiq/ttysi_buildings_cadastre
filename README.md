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

## Binolar va etajlar qanday saqlanadi

```
Hujjatlar/TTYSI Binolar/          <- "Binolar papkasi" (bosh sahifada o'zgartirish mumkin)
├── 1-bino.ttysi                  <- bitta bino = bitta fayl
│     ├── 1-qavat                    (etajlar, ularning chizmasi, AT jihozlari
│     ├── 2-qavat                     va kadastr rasmlari fayl ichida)
│     └── 3-qavat
├── 2-bino.ttysi
│     ├── 1-qavat
│     └── 2-qavat
└── 5-maktab/                     <- tashkilot = papka (bir nechta binoni birlashtiradi)
      ├── 1-bino.ttysi
      └── 2-bino.ttysi
```

- Har bir bino alohida fayl, etajlar esa shu faylning ichida. Binoni boshqa kompyuterga ko'chirish
  yoki yuborish uchun bitta `.ttysi` faylni nusxalash kifoya.
- **Yangi bino** tugmasi nom so'raydi (masalan "3-bino") va faylni avtomatik Binolar papkasida
  yaratadi — "Saqlash" oynasi bilan ovora bo'lish shart emas.
- Bosh sahifa papkadagi **barcha binolarni** o'zi ko'rsatadi; har bir kartada etajlar ro'yxati bor —
  etajni bossangiz, bino shu etajda ochiladi. Papkaga boshqa kompyuterdan `.ttysi` fayl ko'chirsangiz,
  u ham ro'yxatda paydo bo'ladi. Boshqa joydan ochilgan loyihalar "Boshqa joydagi loyihalar" bo'limida.
- **Tashkilotlar.** Bir nechta binoni bitta tashkilotga birlashtirish: bosh sahifada **Yangi tashkilot** —
  nomini yozasiz va birlashtiriladigan binolarni belgilaysiz. Tashkilot bosh sahifada alohida bo'lim
  bo'lib chiqadi (binolar, etajlar va jihozlar soni jami bilan). Bo'lim sarlavhasida: **+ Bino** (yangi
  bino shu tashkilot ichida), **Excel hisobot** (tashkilotning barcha binolari bitta faylda, oxirida
  tashkilot bo'yicha jami) va **⋯** menyusi: binolarni qo'shish, nomini o'zgartirish, papkani ochish,
  tarqatish (binolar o'chirilmaydi, tashkilotsiz bo'lib qoladi). Bino kartasida o'ng tugma —
  **Tashkilotga ko'chirish** yoki **Tashkilotdan chiqarish**. Yangi bino oynasida ham tashkilotni
  tanlash mumkin. Muharrirda bino nomi oldida tashkilot nomi ko'rinadi.
- Muharrirda bino nomi yonidagi **▾** — boshqa binoga tez o'tish.
- Saqlash xavfsiz: fayl avval vaqtinchalik nusxaga yoziladi, keyin almashtiriladi (saqlash vaqtida
  dastur yopilib qolsa ham eski fayl buzilmaydi).

## Dastur oynalari

- **Bosh sahifa** — dastur ochilganda chiqadi. Oxirgi binolar kartalarda ko'rinadi: etajlar soni,
  tayyor etajlar, tasdiqlanmagan belgilar va jihozlar soni. Kartani bosib loyihani ochasiz,
  **Yangi bino** — yangi loyiha va darhol PDF/rasm yuklash. PDF yoki rasmni oynaga sudrab tashlash ham
  mumkin. Kartada o'ng tugma — ro'yxatdan olib tashlash. Muharrirdan qaytish: chap yuqoridagi **AT**
  belgisi yoki `Ctrl+H`.
- **Muharrir** — yuqorida bino nomi (✎ — nomi va manzili), **etaj tablari** (to'q sariq son —
  tasdiqlanmagan belgilar; o'ng tugma — nomini o'zgartirish, surish, qayta chizish, o'chirish),
  `+ Etaj`, bekor qilish/qaytarish va **Eksport**. Ostida **4 ta ish bosqichi** (rasm → xonalar →
  belgilar → eksport) — har birini bosib shu bosqichga o'tasiz. Chapda asboblar va rangli AT jihoz
  tugmalari, o'rtada chizma (kadastr foni, kattalashtirish), o'ngda tanlangan element xususiyatlari va
  etaj bo'yicha jihozlar soni.
- **Suzuvchi AT jihoz paneli** — AT jihoz tugmalarini chizma ustidagi kichik oynaga aylantirish:
  chap paneldagi "AT jihoz" yonidagi **⧉** yoki **Ko'rinish → AT jihoz paneli - suzuvchi oyna** (`F9`).
  Oynani sarlavhasidan ushlab chizmaning qulay joyiga surasiz; `F7` — oynani sichqoncha turgan joyga
  olib keladi. **⇄** (yoki sarlavhani ikki marta bosish) — tik / yotiq ko'rinish. Oynada "Kerak (reja)"
  va **Keyingi ?** (tasdiqlanmagan belgiga o'tish) ham bor. **⇤** yoki yana `F9` — tugmalar chap panelga
  qaytadi. Rejim, joy va ko'rinish eslab qolinadi.
- **Etaj qo'shish ekrani** — PDF bo'lsa, chapda sahifalar; o'rtada etajni ramkaga olasiz (ramka ostida
  etaj o'lchami metrda chiqadi); o'ngda etaj nomi, nisbat, avtomatik chizish va kengaytirilgan
  sozlamalar. **Yaratish va shu PDF'dan yana etaj** — keyingi etajni darhol qo'shish.
- **Eksport oynasi** — format (PDF, PNG/JPG, DXF, Excel, SVG, bir nechta bino bo'yicha Excel), joriy yoki
  barcha etajlar, chizma sozlamalari. Tasdiqlanmagan belgilar bo'lsa ogohlantiradi.

## Ish tartibi

1. **Etaj qo'shish:** `+ Etaj` yoki **Etaj → PDF / rasmdan yangi etaj qo'shish (Ctrl+I).**
   - **PDF:** chapdagi sahifalardan keraklisini tanlaysiz. Bitta sahifada bir nechta etaj bo'lsa,
     keraklisini sichqoncha bilan ramkaga olasiz. Shtampdagi **Nisbat**ni (masalan 1:300) kiritsangiz,
     masshtab avtomatik hisoblanadi va maydonlar m² da chiqadi. Bitta PDF'dan bir nechta etajni
     ketma-ket qo'shish mumkin.
   - **Telefon rasmi:** dastur qog'oz burchaklarini o'zi topadi va perspektivani to'g'rilaydi. Ko'k
     nuqtalarni qo'lda ham surish mumkin. Masshtabni keyin "Masshtabni belgilash" orqali berasiz.
2. **Avtomatik chizish.** Dastur devorlarni topib, xonalar va koridorlarni ko'pburchak qilib chizadi
   va **raqamlaydi** (keyin qo'lda tuzatiladi). Ko'k va qora ruchkadagi qo'lyozma belgilarni esa `?`
   belgisi bilan AT nomzodi sifatida belgilaydi.

   **AT belgilarini alohida aniqlash** (**Etaj → AT belgilarini aniqlash...**, `Ctrl+Shift+M`, etaj
   yorlig'ining menyusi yoki "Belgilarni tasdiqlash" qadami): xonalarga tegmasdan faqat qo'lyozma
   belgilar qayta qidiriladi. Oynada kadastr rasmi va topilgan nomzodlar ko'rinadi (ko'k ruchka — ko'k,
   qora ruchka — qizil ramka); noto'g'ri ramkani bosib chiqarib tashlaysiz. Sozlamalar: ko'k/qora ruchka,
   sezgirlik, "faqat bino ichida", natija `?` lar o'rniga yoki mavjudlariga qo'shilsin. Qora ruchka
   kulrang (nusxa) bosma chizmadan to'q va qalin izi, qiya/egri chiziqlari bo'yicha ajratiladi; devor
   ustiga yozilgan belgi ham topiladi. Toza qora bosma PDF'da qora qo'lyozma qidirilmaydi.
3. **Belgilarni tasdiqlash ekrani.** Etaj qo'shilgach, `?` belgilar bo'lsa, tasdiqlash ekrani o'zi
   ochiladi (keyin ham: **Tahrirlash → Belgilarni tasdiqlash**, `Ctrl+T`, yoki o'ng paneldagi
   "Tasdiqlash" havolasi). Har bir belgi uchun kadastr rasmining kattalashtirilgan bo'lagi ko'rsatiladi
   (belgi qizil punktir doira ichida) va qaysi xonada ekani yoziladi:
   - `1`–`6` yoki katta tugmalar — jihoz turi (keyingi belgiga o'zi o'tadi);
   - `Q` — holat: mavjud / kerak (rejada);
   - `Del` — "belgi emas" (o'chiriladi), `N` — o'tkazib yuborish (navbat oxiriga);
   - pastda navbatdagi belgilar ko'rinadi, yuqorida — nechtasi qolgani.

   Hamma o'zgarishlar `Ctrl+Z` bilan bekor qilinadi. Topilmay qolgan belgilarni chap paneldan qo'lda
   qo'yasiz.
4. **Tuzatish:**
   - burchaklarni sudrash;
   - qirrani ikki marta bosib yangi burchak qo'shish;
   - `B` — xonani chiziq bilan bo'lish;
   - `Ctrl+M` — xonalarni birlashtirish;
   - `P` / `R` — yangi xona chizish;
   - o'ng tugma — xona turini tanlash (xona, koridor, kompyuter xona, zinapoya, hojatxona);
   - `L` — **devor**: xona chegarasidan tashqari alohida devor yoki to'siq. Burchaklarni ketma-ket
     bosasiz, `Enter` yoki ikki marta bosish bilan tugatasiz.
     Burchaklari sudraladi, qirraga ikki marta bosib yangi burchak qo'shiladi. Eshik bu devorga
     ham yopishadi;
   - **Devor qalinligi:**
     - tanlangan devor(lar): o'ngdagi panelda aniq qiymat (0.05–1.50 m, 1 sm qadam) yoki
       `Alt+↑` / `Alt+↓` (±5 sm); bir nechta devor tanlansa, hammasiga qo'llanadi;
     - xona devorlari: hech narsa tanlanmaganda paneldagi "Xona devorlari" (shu etaj uchun);
     - yangi devorlar: paneldagi "Yangi devorlar" — Devor asbobi shu qalinlikda chizadi;
   - `D` — **eshik**: devorga bosasiz va u eng yaqin devorga yopishadi. Sudrab boshqa devorga
     ko'chirish mumkin. O'ng tugma menyusida: bir yoki ikki tabaqali, ochilish tomoni, sharnir tomoni,
     kengligi (0.8–1.8 m);
   - `Z` — **zina**: maydonini to'rtburchak qilib torting. Ichida pog'onalar va yo'nalish strelkasi
     chiziladi. **Yo'nalishi** (strelka — ko'tarilish tomoni) qo'lda o'zgartiriladi: o'ngdagi panelda
     "Zina yo'nalishi" (→ ↓ ← ↑ yoki avtomatik), **↻ 90°** tugmasi yoki o'ng tugma menyusi;
   - `O` — **gumbaz (doira bino)**, masalan institutga kirish-chiqish (o'tish) binolari: sichqonchani
     bosib torting — doira chiziladi (`Shift` — ellips). Gumbaz ichida punktir halqa bilan belgilanadi,
     DXF'da `GUMBAZ` qatlamida. Doiraning burchak nuqtalari yo'q — o'lchami atrofidagi tutqichlar yoki
     paneldagi "eni × bo'yi" bilan o'zgartiriladi. Kadastr rasmida aylana devorli bino bo'lsa,
     **avtomatik chizish uni o'zi topadi**: ichki devor chizig'i bo'yicha doira xona va devordagi
     kirish-chiqish bo'shliqlariga eshiklar (kengi ikki tabaqali) qo'yiladi;
   - **Eshik ochilish tomoni**: eshikni devorning qaysi tarafiga bossangiz (yoki sudrab o'tkazsangiz),
     o'sha tarafga ochiladi. Ikki marta bosish — tomonini almashtirish. **Kengligi**: eshik chetidagi
     oq tutqichlarni sudrang yoki o'ngdagi panelda aniq qiymat (0.5–4 m) kiriting;
   - **O'lchamni o'zgartirish**: xona, zina yoki devor tanlanganda atrofida 8 ta oq tutqich chiqadi —
     burchakdagisi ikki tomonga, qirradagisi bir tomonga cho'zadi (qarama-qarshi tomon joyida qoladi,
     `Shift` — nisbatni saqlash). Ko'k nuqtalar esa alohida burchakni suradi. Aniq o'lcham: o'ngdagi
     panelda "eni × bo'yi" (metrda);
   - **Istalgan burchakka burish**: xona, zina, gumbaz yoki devor tanlanganda tepasida aylana tutqich
     chiqadi — sudrab istalgan burchakka burasiz (`Shift` — 15° qadam). O'ngdagi panelda "Burish
     (istalgan burchak)" maydoniga masalan `37.5` yozib **Burish** (eshik uchun ham);
   - **Kattalashtirish / kichiklashtirish**: `Ctrl+Alt+=` / `Ctrl+Alt+-` — tanlangan elementlar 10%
     ga (o'z markazi atrofida; eshik — kengligi). Faqat AT belgilari tanlangan bo'lsa — etajdagi
     belgilar o'lchami o'zgaradi (hech narsa tanlanmaganda paneldagi "AT belgilari o'lchami").
   - **Joyida aylantirish:** tanlangan xona, zina yoki eshik o'z markazi atrofida buriladi. `]` —
     90° o'ngga, `[` — 90° chapga, `Ctrl+Shift+R` — istalgan burchak. O'ng tugma menyusida esa
     "Aylantirish" bo'limi bor.
5. **Mavjud va kerak jihozlar.** Har bir jihozning holati bor:
   - **Mavjud** — chizmada to'liq rangli belgi;
   - **Kerak (o'rnatilishi rejada)** — oq fonli, punktir chegarali belgi.

   Holatni o'zgartirish usullari: jihozni tanlab `Ctrl+K`, o'ng tugma menyusi yoki xususiyatlar
   paneli. Asboblar panelidagi **"Kerak (reja)"** (`Q`) yoqilsa, yangi qo'yilgan jihozlar darhol
   "kerak" bo'ladi. Masalan: kompyuter xonasida internet yo'q bo'lsa, xona turini "Kompyuter xona"
   qilasiz va unga "kerak" holatidagi Switch qo'yasiz.
6. **Kadastr rasmini almashtirish** (etaj tabida o'ng tugma yoki **Etaj → Kadastr rasmini
   almashtirish**): yangi PDF yoki rasm tanlanadi, ramkaga olinadi, nisbat kiritiladi. Chizma o'z
   joyida qoladi (yangi rasm o'lchamiga moslanadi). Xohlasangiz "Xonalarni yangi rasmdan qayta chizish"
   ni belgilang — xonalar yangidan topiladi, turi tasdiqlangan AT belgilari, eshik va devorlar saqlanadi.
   **Etaj → Kadastr rasmini olib tashlash** — faqat fon rasmini o'chiradi.
7. **Klaviatura tugmalari (Yordam → Klaviatura tugmalari, `Ctrl+,`).** Har bir amalning tugmasini
   o'zingizga qulay qilib almashtirasiz: maydonni bosib, yangi tugmani bosing. Bir xil tugma ikki
   amalga berilsa, ikkalasi qizil bilan ko'rsatiladi va saqlab bo'lmaydi. "Standart" tugmasi bitta
   amalni, "Hammasini standartga qaytarish" esa barchasini asl holiga qaytaradi. O'zgartirilgan
   tugmalar menyularda, maslahatlarda, qo'llanmada va tasdiqlash ekranida darhol yangilanadi va
   kompyuterda saqlanib qoladi. Bu yerda yozilgan tugmalar — standart qiymatlar.
8. **Nisbat va masshtab.** Hech narsa tanlanmaganda o'ngdagi panelda **"Nisbat"** maydoni: `1 : 200`,
   `1 : 300`, `1 : 400` ... yozing yoki yonidagi ro'yxatdan tanlang. PDF'dan olingan etajda masshtab darhol
   qayta hisoblanadi. **"Qayta hisoblash"** tugmasi (yoki sarlavhadagi "masshtab yo'q — qayta hisoblash"
   havolasi, Etaj menyusi): nisbat va rasm aniqligi (PDF/skaner, odatda 200 DPI) bo'yicha masshtab va
   barcha maydonlar qayta hisoblanadi — oldingi versiyalarda qo'shilgan etajlar uchun ham. Telefon
   rasmida "2 nuqta bilan" — uzunligi ma'lum chiziq bo'yicha; shundan keyin nisbat o'zgarsa o'zi
   qayta hisoblanadi. Etaj sarlavhasida nisbat ko'rinadi (1:300).
   **Kadastr fonini moslash** (shu panel yoki Etaj menyusi): **✥ Surish** — rasmni sichqoncha bilan
   suring; **⌖ 2 nuqta bilan moslash** — rasmdagi nuqtani, keyin chizmadagi mos joyni bosing (2 marta),
   fon surilib, burilib va kattalashib o'z joyiga tushadi; **Burilish / O'lchami** — aniq qiymat;
   **Fonni asl holiga qaytarish**. Moslash `Ctrl+Z` bilan bekor qilinadi, eksportda va qayta chizishda
   ham hisobga olinadi.
9. **Masshtab (Etaj menyusi).** Uzunligi ma'lum devorni belgilasangiz, maydonlar m² da chiqadi va DXF
   metrlarda saqlanadi.
10. **Eksport** (yuqoridagi tugma yoki `Ctrl+E`):
   - PNG / JPG va SVG (barcha etajlar tanlansa — har etaj alohida fayl, tanlangan papkaga);
   - PDF (joriy etaj yoki barcha etajlar bitta faylda);
   - "Rejadagi (kerak) jihozlar" belgisini olib tashlasangiz, faqat mavjud jihozlar chiqadi;
   - DXF (AutoCAD; qatlamlar `XONA_*` va `AT_*`, jihozlar bloklar sifatida);
   - **Excel hisobot** — joriy bino yoki bir nechta bino (`.ttysi` fayllar) bo'yicha: etajlar
     kesimida mavjud jihozlar soni, har bir xonadagi jihozlar, jihozlarning to'liq ro'yxati va
     **"Kerak (reja)"** varag'i: qaysi bino, etaj va xonaga nima o'rnatish kerakligi.
   - DXF'da rejadagi jihozlar alohida `AT_<kod>_KERAK` qatlamida, punktir chiziq bilan chiqadi.
     Eshiklar `ESHIKLAR`, zina pog'onalari `ZINALAR`, alohida devorlar esa `DEVORLAR` qatlamida
     (haqiqiy qalinlikda) bo'ladi.
   - **Eksport jarayoni oynasi:** qaysi etaj/sahifa yozilayotgani va umumiy holat ko'rinib turadi.
     Oxirida natija: **"Eksport tugadi ✓"** (yashil), **"Qisman bajarildi"** (sariq) yoki
     **"Eksport bajarilmadi"** (qizil) va har bir fayl bo'yicha xabar — masalan "fayl boshqa dasturda
     ochiq, yoping va qayta urinib ko'ring". **Qayta urinish** faqat xato bo'lgan fayllarni qayta
     yozadi; **Faylni ochish** / **Papkani ochish** tayyor natijani ochadi. Bir fayldagi xato
     qolganlarini to'xtatmaydi; "Bekor qilish" joriy fayl tugagach to'xtatadi.

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

## Yangilash

Dastur o'zini o'zi yangilaydi, yangi versiya uchun `.exe` ni qayta yig'ish va tarqatish shart emas.

Hech narsa qilish shart emas — hammasi o'zi bo'ladi:

1. Dastur ochilganda (va ochiq tursa, har 6 soatda) yangi versiya fonda tekshiriladi.
2. **Kichik kod yangilanishi** (~200 KB, ko'p holatda shu) so'ramasdan fonda yuklanadi. Oyna tepasida
   ko'k panel chiqadi: *"Versiya X tayyor"* — **Qayta ochish** tugmasi (ochiq loyiha ham qayta ochiladi).
   Bosmasangiz ham, keyingi safar dastur ochilganda yangi versiya ishlaydi.
3. **To'liq paket** (~110 MB) faqat kutubxonalar o'zgarganda kerak bo'ladi — panelda
   **Yuklab o'rnatish** tugmasi chiqadi; yuklangach dastur yopilib, almashtirilib, qayta ochiladi.
4. Yangilangandan keyin birinchi ochilishda **"Nima yangi"** oynasi ko'rsatiladi.

Xavfsizlik: har bir fayl SHA-256 bilan tekshiriladi; tarmoq uzilsa yuklash 3 marta qayta urinadi;
yangi kod ishga tushmasa, dastur o'zi avvalgi ishlaydigan versiyaga qaytadi va keyingi safar to'liq
paket taklif qiladi. Qo'lda tekshirish: **Yordam → Yangilanishni tekshirish** (bitta oynada holat,
"nima yangi" va yuklash jarayoni).

**Yangilanish manbai** (Yordam → Yangilanish sozlamalari):
- **Tarmoq yoki mahalliy papka** — institut ichida internetsiz ishlaydi. Relizdagi uchta faylni
  (`update.json`, `ttysi_app-<versiya>.zip`, `TTYSI_Kadastr_Windows.zip`) masalan
  `\\server\TTYSI\yangilanish` papkasiga ko'chiring va dasturlarda shu papkani ko'rsating.
- Sozlamalar oynasidagi **Ulanishni tekshirish** tugmasi kiritilgan manba/token ishlashini darhol
  ko'rsatadi (saqlamasdan). Xato bo'lsa, sababi aniq yoziladi (token eskirgan, ruxsat yo'q, limit va h.k.).
- **Internet (GitHub)** — standart. Repozitoriy ochiq bo'lsa hech qanday sozlash kerak emas. Yopiq
  bo'lsa, "Qo'shimcha" bo'limida faqat o'qish huquqli (Contents: Read-only) fine-grained token kiritiladi.

**Yangi versiya chiqarish (dasturchi uchun):** `ttysi_cadastre/__init__.py` dagi `__version__` ni
oshiring va commit xabariga `[release]` qo'shing. GitHub Actions testlarni o'tkazadi, `.exe` ni
yig'adi va sinaydi, keyin reliz va yangilanish fayllarini chiqaradi. Commit xabari foydalanuvchiga
"yangilikda nima bor" bo'lib ko'rinadi.

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
