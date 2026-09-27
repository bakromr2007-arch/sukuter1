import os

# .env yoki Render Environment sozlamalaridan olinadi
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///scooter.db")
# WebApp joylashtirilgan URL (Render'dagi backend manzili, https bo'lishi shart)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app.onrender.com")
# @username (bot.py ishga tushganda konsolga chiqaradi, shuni shu yerga qo'ying)
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
