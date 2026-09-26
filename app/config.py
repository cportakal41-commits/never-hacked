import os
from datetime import timedelta
from dotenv import load_dotenv

# .env dosyasini yukle
load_dotenv()

# Render.com postgres:// -> postgresql+psycopg2:// duzeltmesi
_db_url = os.getenv('DATABASE_URL', 'postgresql+psycopg2://postgres:postgres@db:5432/never_hacked')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql+psycopg2://', 1)
elif _db_url.startswith('postgresql://') and not _db_url.startswith('postgresql+'):
    _db_url = _db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)


class Config:
    # --- Genel Ayarlar ---
    SECRET_KEY = os.getenv('SECRET_KEY', 'CHANGE_ME')
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'CHANGE_ME')
    _admin_env = os.getenv('ADMIN_PASSWORD')
    ADMIN_PASSWORD = _admin_env.strip() if _admin_env and _admin_env.strip() else 'NeverHacked2026!'

    # Veritabani baglantisi
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- JWT Ayarlari ---
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # --- Rate Limiting ---
    RATELIMIT_HEADERS_ENABLED = True

    # --- Loglama ---
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
