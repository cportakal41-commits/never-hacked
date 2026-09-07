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
            db.create_all()
            from .models import Token
            if not Token.query.first():
                demo = Token(key="NH-DEMO-2026-KEY", note="İlk Demo Anahtarı")
                db.session.add(demo)
                db.session.commit()
        except Exception as e:
            logging.warning(f"Otomatik tablo oluşturma atlandı: {e}")

    # ── JWT Blocklist callback ─────────────────────────────────────────────────
    from .services.token_manager import is_token_revoked
    jwt.token_in_blocklist_loader(is_token_revoked)

    # ── Blueprint'leri kaydet ──────────────────────────────────────────────────
    from .resources.auth import auth_bp
    from .resources.search import search_bp
    from .resources.admin import admin_bp

    app.register_blueprint(auth_bp,   url_prefix="/api")    # /api/login, /api/me, /api/logout
    app.register_blueprint(search_bp, url_prefix="/api")    # /api/search
    app.register_blueprint(admin_bp,  url_prefix="/api/admin")  # /api/admin/...

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

    return app
