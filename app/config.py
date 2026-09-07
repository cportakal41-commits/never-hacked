import os
from datetime import timedelta

# Render.com postgres:// → postgresql:// düzeltmesi
# (SQLAlchemy 1.4+ artık postgres:// kabul etmiyor)
_db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/never_hacked")
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)


class Config:
    # ─── Genel Ayarlar ──────────────────────────────────────────────────────────
    SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_ME")

    # Veritabanı bağlantısı (varsayılan: Docker Compose'daki postgres servisi)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # Gereksiz bellek kullanımını engeller

    # ─── JWT Ayarları ───────────────────────────────────────────────────────────
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)    # Erişim token ömrü: 8 saat
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)   # Yenileme token ömrü: 30 gün

    # ─── Rate Limiting ──────────────────────────────────────────────────────────
    RATELIMIT_HEADERS_ENABLED = True  # Yanıt başlıklarında limit bilgisini göster

    # ─── Loglama ────────────────────────────────────────────────────────────────
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
