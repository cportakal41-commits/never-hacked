import pytest
from app import create_app, db as _db
from app.models import User, Token


@pytest.fixture(scope="session")
def app():
    """Test uygulama fabrikası – SQLite in-memory veritabanı kullanır."""
    test_app = create_app()
    test_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret",
        "SECRET_KEY": "test-secret",
    })
    with test_app.app_context():
        _db.create_all()
        yield test_app
        _db.drop_all()


@pytest.fixture()
def client(app):
    """Flask test istemcisi."""
    return app.test_client()


# ─── Sağlık kontrolü testi ─────────────────────────────────────────────────

def test_health(client):
    """GET /health → 200 OK döndürmeli."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ─── Kimlik doğrulama testleri ─────────────────────────────────────────────

def test_login_invalid_mid(client):
    """Sayısal olmayan MID 400 döndürmeli."""
    resp = client.post("/api/login", json={"mid": "abc"})
    assert resp.status_code == 400


def test_login_missing_body(client):
    """Boş gövde 400 döndürmeli."""
    resp = client.post("/api/login", data="not json",
                       content_type="text/plain")
    assert resp.status_code == 400


def test_search_without_token(client):
    """Token olmadan /api/search 401 döndürmeli."""
    resp = client.get("/api/search?mid=123456")
    assert resp.status_code == 401


def test_search_invalid_mid_with_token(client, app):
    """Geçersiz MID ile arama 400 döndürmeli."""
    from flask_jwt_extended import create_access_token
    with app.app_context():
        # Test kullanıcısı oluştur
        user = User(mid=999999, nick="testuser")
        _db.session.add(user)
        _db.session.commit()
        token = create_access_token(identity=user.id)

    resp = client.get(
        "/api/search?mid=abc",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 400
