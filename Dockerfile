FROM python:3.11-slim

WORKDIR /app

# Tizim kutubxonalari (psycopg2 kabi paketlar uchun)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite fayli va yuklangan videolar shu yerga yoziladi — volume sifatida ulang
RUN mkdir -p /app/data /app/uploads
ENV DATABASE_URL=sqlite:////app/data/scooter.db

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
