# Never Hacked – README

## Proje Hakkında

Hazaclub kullanıcılarını MID numarası ile sorgulayan, JWT tabanlı kimlik doğrulaması kullanan Flask web uygulaması.

## Özellikler

- **JWT Kimlik Doğrulama** – erişim token'ı (8 saat), sunucu taraflı revokasyon
- **Hazaclub API** – anlık kullanıcı bilgisi çekme
- **Flask-Admin** – CRUD arayüzü (`/admin-panel`)
- **Yeşil Hacker Teması** – Orbitron font, matrix arka plan, glow efektleri
- **Docker** – tek komutla çalıştırma

## Hızlı Başlangıç

```bash
# 1. .env dosyası oluştur
cp .env.example .env
# .env içindeki değerleri düzenle

# 2. Docker ile başlat
docker compose up -d

# 3. Tarayıcıda aç
# http://localhost:5000
```

## API Endpoint'leri

| Yöntem | URL | Açıklama |
|--------|-----|----------|
| POST | `/api/login` | Giriş → JWT token |
| GET  | `/api/me` | Profil bilgisi |
| DELETE | `/api/logout` | Oturumu kapat |
| GET  | `/api/search?mid=<mid>` | Kullanıcı ara |
| GET  | `/api/admin/users` | Kullanıcı listesi (admin) |
| GET  | `/api/admin/tokens` | Token listesi (admin) |
| POST | `/api/admin/tokens/revoke/<id>` | Token revoke (admin) |
| POST | `/api/admin/tokens/revoke-user/<uid>` | Kullanıcı tokenları revoke |
| GET  | `/health` | Sağlık kontrolü |

## Yerel Geliştirme (Docker olmadan)

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
set FLASK_APP=app
set DATABASE_URL=sqlite:///dev.db
flask db upgrade
flask run
```

## Testler

```bash
pip install pytest
pytest tests/ -v
```

## Güvenlik Notları

- `.env` dosyasını asla sürüm kontrolüne eklemeyin
- Üretimde HTTPS kullanın (NGINX / Traefik)
- `SECRET_KEY` ve `JWT_SECRET_KEY` değerlerini güçlü rastgele değerlerle değiştirin
- Admin paneline erişimi IP kısıtlamasıyla koruyun
