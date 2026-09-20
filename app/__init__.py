import logging
import logging.config
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from .config import Config

# ─── Uzantı örnekleri (uygulama bağımsız) ────────────────────────────────────
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app() -> Flask:
    """
    Flask uygulama fabrikası.

    Tüm uzantıları, Blueprint'leri ve JWT callback'lerini burada kaydeder.
    Test ortamında farklı bir config nesnesi geçilebilir.
    """
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    # ── Loglama yapılandırması ─────────────────────────────────────────────────
    logging.basicConfig(
        level=app.config.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # ── Uzantıları başlat ──────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # ── Veritabanı tablolarını ve varsayılan token'ı otomatik hazırla ──────────
    with app.app_context():
        try:
            # 1. Modelleri SQLAlchemy metadata'sına kaydetmek için önce içe aktar
            from .models import User, Token, BlockedId, TreasureScanLog, RewardCooldown
            db.create_all()

            # 2. PostgreSQL için otomatik şema güncellemesi (mevcut tabloda eksik kolon varsa ekle)
            if db.engine.dialect.name == "postgresql":
                from sqlalchemy import text
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE tokens ADD COLUMN IF NOT EXISTS "key" VARCHAR(64);'))
                    conn.execute(text('ALTER TABLE tokens ADD COLUMN IF NOT EXISTS note VARCHAR(128) DEFAULT \'Genel Erişim\';'))
                    conn.execute(text('ALTER TABLE tokens ADD COLUMN IF NOT EXISTS usage_count INTEGER DEFAULT 0;'))
                    conn.execute(text('ALTER TABLE tokens ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP;'))
                    conn.execute(text('ALTER TABLE tokens ADD COLUMN IF NOT EXISTS jti VARCHAR(36);'))
                    conn.execute(text('ALTER TABLE tokens ADD COLUMN IF NOT EXISTS revoked BOOLEAN DEFAULT FALSE;'))
                    conn.execute(text('UPDATE tokens SET "key" = \'NH-DEMO-\' || id WHERE "key" IS NULL;'))
                    conn.execute(text('UPDATE tokens SET usage_count = 0 WHERE usage_count IS NULL;'))
                    conn.execute(text('UPDATE tokens SET revoked = FALSE WHERE revoked IS NULL;'))
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_tokens_key ON tokens ("key");'))
                    conn.execute(text('''
                        CREATE TABLE IF NOT EXISTS blocked_ids (
                            id SERIAL PRIMARY KEY,
                            mid INTEGER UNIQUE NOT NULL,
                            note VARCHAR(255) DEFAULT 'Admin tarafından kısıtlı erişim',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    '''))
                    conn.execute(text('''
                        CREATE TABLE IF NOT EXISTS treasure_scan_logs (
                            id SERIAL PRIMARY KEY,
                            token_key VARCHAR(64) NOT NULL,
                            token_note VARCHAR(128) DEFAULT 'Genel Kullanıcı',
                            found_summary VARCHAR(255) DEFAULT 'Hedef ödül bulunamadı',
                            raw_results TEXT DEFAULT '[]',
                            pages_scanned INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    '''))
                    conn.execute(text('''
                        CREATE TABLE IF NOT EXISTS reward_cooldowns (
                            id SERIAL PRIMARY KEY,
                            token_key VARCHAR(64) NOT NULL,
                            reward_id INTEGER NOT NULL,
                            reward_name VARCHAR(64) NOT NULL,
                            last_found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            cooldown_until TIMESTAMP NOT NULL
                        );
                    '''))
                    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_treasure_scan_logs_token ON treasure_scan_logs (token_key);'))
                    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_reward_cooldowns_token ON reward_cooldowns (token_key);'))
                    conn.commit()

            # 3. Varsayılan Demo Token'ı kontrol et ve ekle
            demo_token = Token.query.filter_by(key="NH-DEMO-2026-KEY").first()
            if not demo_token:
                demo = Token(key="NH-DEMO-2026-KEY", note="İlk Demo Anahtarı")
                db.session.add(demo)
                db.session.commit()
                logging.info("Varsayılan NH-DEMO-2026-KEY anahtarı hazırlandı.")
        except Exception as e:
            logging.error(f"Veritabanı başlatma/güncelleme hatası: {e}", exc_info=True)

    # ── JWT Blocklist callback ─────────────────────────────────────────────────
    from .services.token_manager import is_token_revoked
    jwt.token_in_blocklist_loader(is_token_revoked)

    # ── Blueprint'leri kaydet ──────────────────────────────────────────────────
    from .resources.auth import auth_bp
    from .resources.search import search_bp
    from .resources.admin import admin_bp
    from .resources.treasure import treasure_bp

    app.register_blueprint(auth_bp,     url_prefix="/api")         # /api/login, /api/me, /api/logout
    app.register_blueprint(search_bp,   url_prefix="/api")         # /api/search
    app.register_blueprint(treasure_bp, url_prefix="/api")         # /api/treasure/scan, /api/treasure/status
    app.register_blueprint(admin_bp,    url_prefix="/api/admin")   # /api/admin/...

    # ── Flask-Admin UI ─────────────────────────────────────────────────────────
    from .models import User, Token
    admin_ui = Admin(
        app,
        name="Never Hacked Admin",
        template_mode="bootstrap3",
        url="/admin-panel",   # /admin ile Blueprint çakışmasını önler
    )
    admin_ui.add_view(ModelView(User,  db.session, name="Kullanıcılar"))
    admin_ui.add_view(ModelView(Token, db.session, name="Token'lar"))

    # ── Ana sayfa ──────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        """Tek sayfalık ön-yüz uygulamasını sunar."""
        return app.send_static_file("index.html")

    # ── Özel Hacker Temalı Admin Paneli ────────────────────────────────────────
    @app.route("/admin")
    def admin_dashboard():
        """Hacker temalı özel admin konsolunu sunar."""
        return app.send_static_file("admin.html")

    # ── Sağlık kontrolü endpoint'i ─────────────────────────────────────────────
    @app.route("/health")
    def health():
        """Docker/Kubernetes probe'ları için basit sağlık yanıtı."""
        return {"status": "ok"}, 200

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.after_request
    def add_cache_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app
