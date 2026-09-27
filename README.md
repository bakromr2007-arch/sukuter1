# Skuter Ijara Boti

Skuterlarni ijaraga berish, to'lovlarni kuzatish va qarzdorlikni avtomatik
eslatib turish uchun tizim. **Butun boshqaruv — mijoz qo'shish, to'lov qayd
qilish, qarzdorlar ro'yxati — Telegram WebApp ichida, tugmalar orqali**
amalga oshiriladi. Bot faqat: mijozni ro'yxatdan o'tkazadi, WebApp tugmasini
beradi va kunlik eslatmalarni yuboradi.

## Fayllar

- `bot.py` — Telegram bot (`/start`, ro'yxatdan o'tish, eslatmalar)
- `webapp_api.py` — WebApp backend (`/api/...` endpointlar) + `webapp/` papkasini beradi
- `app.py` — **Render uchun yagona kirish nuqtasi**: bot va webapp'ni bitta process ichida birga ishga tushiradi
- `models.py`, `database.py` — ma'lumotlar bazasi (hozircha SQLite)

## Qanday ishlaydi

1. **Siz (admin)** botni ochasiz → "📱 Ochish" tugmasi → Nazorat paneli
   ochiladi. "Yangi mijoz" bo'limida skuter, mijoz ma'lumotlari, kunlik
   narx va video arizani to'ldirasiz.
2. Tizim sizga ro'yxatdan o'tish havolasini beradi — shuni mijozga yuborasiz.
3. Mijoz havolani bosib botni ishga tushirganda, avtomatik faollashadi va
   WebApp orqali o'z holatini ko'rish imkoniyati ochiladi.
4. To'lov qabul qilganingizda, "Nazorat" bo'limida mijoz ustiga bosib
   summani kiritasiz — tizim avtomatik hisoblab, mijozga xabar yuboradi.
5. Har kuni soat 09:00 da qarzi bor mijozlarga eslatma ketadi.

## Render'ga joylashtirish (bitta xizmat)

Bot va WebApp bitta SQLite faylini bo'lishgani uchun ularni **bitta Render
Web Service** sifatida, `app.py` orqali birga ishga tushiramiz.

1. Kodni GitHub'ga yuklang.
2. Render'da **New +** → **Web Service** → repo'ni tanlang.
3. Sozlamalar:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. **Environment** bo'limiga quyidagilarni qo'shing:
   - `BOT_TOKEN` — BotFather'dan olingan token
   - `ADMIN_ID` — sizning Telegram ID'ingiz (masalan @userinfobot orqali bilib oling)
   - `BOT_USERNAME` — botingiz username'i (`@` belgisisiz)
   - `WEBAPP_URL` — deploy tugagach Render bergan https manzil (masalan `https://skuter-bot.onrender.com`) — birinchi marta bo'sh joylashtirib, keyin URL chiqqach qo'shib, qayta deploy qilsangiz ham bo'ladi
   - `DATABASE_URL` — hozircha kerak emas, qo'ymasangiz avtomatik `sqlite:///scooter.db` ishlatiladi
5. Deploy tugagach, `@BotFather` → botingiz → **Bot Settings** → **Menu Button** →
   WEBAPP_URL bilan bir xil havolani kiriting.

### Muhim: SQLite va disk

Render'ning oddiy Web Service'i **doimiy disk emas** — har safar qayta
deploy qilinganda yoki instance qayta ishga tushganda `scooter.db` fayli
(va yuklangan video-arizalar) **o'chib ketishi mumkin**.

- Agar bu siz uchun muhim bo'lsa (ma'lumotlar yo'qolmasligi kerak bo'lsa),
  Render'da shu xizmatga **Persistent Disk** qo'shing (Render dashboard →
  xizmat → **Disks** → Add Disk, masalan `/data` yo'liga bog'lang) va
  `DATABASE_URL=sqlite:////data/scooter.db` qiling.
- Yoki keyinroq PostgreSQL'ga o'tsangiz bo'ladi — kodni o'zgartirish shart
  emas, faqat `DATABASE_URL`ni Postgres manziliga almashtirasiz.

## Docker orqali ishga tushirish

Loyihada tayyor `Dockerfile` va `docker-compose.yml` bor — bot va webapp
bitta konteynerda, `app.py` orqali birga ishlaydi.

```bash
cp .env.example .env
# .env faylni to'ldiring: BOT_TOKEN, ADMIN_ID, BOT_USERNAME, WEBAPP_URL

docker compose up -d --build
```

- `scooter.db` fayli va yuklangan videolar `./data` va `./uploads`
  papkalariga (kompyuteringizda) saqlanadi — konteyner o'chirilsa ham
  ma'lumot yo'qolmaydi.
- `WEBAPP_URL` https bo'lishi shart (Telegram talab qiladi). VPS'da domen
  va SSL bo'lsa to'g'ridan-to'g'ri ishlaydi; lokalda sinash uchun ngrok
  kerak bo'ladi.

Faqat Docker (compose'siz) ishlatmoqchi bo'lsangiz:

```bash
docker build -t skuter-bot .
docker run -d --env-file .env -p 8000:8000 \
  -v $(pwd)/data:/app/data -v $(pwd)/uploads:/app/uploads \
  skuter-bot
```

Render'da ham shu `Dockerfile`dan foydalanish mumkin: **New +** →
**Web Service** → repo tanlang → Render Dockerfile'ni avtomatik topadi
(Environment bo'limida `BOT_TOKEN`, `ADMIN_ID`, `BOT_USERNAME`,
`WEBAPP_URL`ni qo'shing; ma'lumot saqlanishi uchun Persistent Disk'ni
`/app/data` yo'liga bog'lang).

## Lokal ishga tushirish (Docker'siz)

```bash
pip install -r requirements.txt
```

`.env` fayl yarating:

```
BOT_TOKEN=1234567890:AA...
ADMIN_ID=123456789
BOT_USERNAME=sizning_botingiz
DATABASE_URL=sqlite:///scooter.db
WEBAPP_URL=https://sizning-ngrok-yoki-render-manzilingiz
```

Bitta buyruq bilan (Render'dagi kabi) ishga tushiring:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

WebApp tugmasini lokalda sinash uchun `WEBAPP_URL` https bo'lishi kerak —
[ngrok](https://ngrok.com) orqali https havola oling (`ngrok http 8000`)
va shu havolani `WEBAPP_URL`ga qo'ying.

## Keyingi qadamlar (xohlasangiz)

- Persistent Disk yoki PostgreSQL'ga o'tish (ma'lumotlar yo'qolmasligi uchun)
- Onlayn to'lov (Payme/Click) integratsiyasi
- Bir nechta admin/xodim qo'shish
- Skuterlar uchun alohida holat (ta'mirda, band, bo'sh) kuzatuvi
