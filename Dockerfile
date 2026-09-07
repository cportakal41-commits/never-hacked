# Slim Python 3.11 tabanlı resmi imaj
FROM python:3.11-slim

# Güvenlik: root olmayan kullanıcı oluştur
RUN useradd --create-home appuser
WORKDIR /app

# Bağımlılıkları önce kopyala (katman önbelleği için)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodunu kopyala
COPY . .

# Sahipliği appuser'a ver
RUN chown -R appuser:appuser /app
USER appuser

# Flask uygulama modülünü belirt
ENV FLASK_APP=app

# Üretim WSGI sunucusu
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers=2", "--timeout=60", "app:create_app()"]
