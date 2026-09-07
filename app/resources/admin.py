import logging
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from .. import db
from ..models import Token, User

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin_api", __name__)


import hashlib

def get_current_admin_password() -> str:
    """Aktif admin şifresini güvenle döndürür."""
    p = current_app.config.get("ADMIN_PASSWORD")
    if p and str(p).strip():
        return str(p).strip()
    return "NeverHacked2026!"


def generate_admin_token(secret: str) -> str:
    """Admin şifresi için güvenli hash oturum anahtarı üretir."""
    salt = current_app.config.get("SECRET_KEY", "never_hacked_salt")
    return hashlib.sha256(f"{salt}_{secret}".encode()).hexdigest()


# ─── Admin Kimlik Doğrulama Dekoratörü ─────────────────────────────────────────
def admin_required(f):
    """Admin paneli endpoint'lerini korur. Şifre veya admin token zorunludur."""
    @wraps(f)
    def decorated(*args, **kwargs):
        expected_pass = get_current_admin_password()
        expected_tok = generate_admin_token(expected_pass)

        # Gelen anahtar (X-Admin-Key, X-Admin-Password veya Authorization Header)
        auth_val = (
            request.headers.get("X-Admin-Key") or
            request.headers.get("X-Admin-Password") or
            request.headers.get("Authorization", "")
        ).strip()

        if auth_val.startswith("Bearer "):
            auth_val = auth_val[7:].strip()

        # Doğrudan şifre veya geçerli admin session token'ı eşleşiyorsa izin ver!
        if auth_val and auth_val in (expected_pass, expected_tok):
            return f(*args, **kwargs)

        # Alternatif JWT kontrolü
        if auth_val:
            try:
                from flask_jwt_extended import decode_token
                decoded = decode_token(auth_val)
                if decoded.get("sub") == "admin" or decoded.get("is_admin") is True:
                    return f(*args, **kwargs)
            except Exception:
                pass

        return jsonify({"msg": "Yetkisiz erişim! Lütfen admin şifresi ile giriş yapınız."}), 401
    return decorated


# ─── Admin Giriş Endpoint'i ───────────────────────────────────────────────────
@admin_bp.route("/login", methods=["POST"])
def admin_login():
    """Admin şifresi doğrulaması yapar ve admin oturum token'ı döner."""
    data = request.get_json(silent=True) or {}
    password = str(data.get("password") or "").strip()
    expected_pass = get_current_admin_password()

    if not password or password != expected_pass:
        logger.warning("Admin login denemesi başarısız: şifre uyuşmuyor.")
        return jsonify({"msg": "Hatalı yönetici şifresi!"}), 401

    admin_token = generate_admin_token(expected_pass)
    logger.info("Admin paneline başarılı giriş yapıldı.")
    return jsonify({
        "msg": "Giriş başarılı",
        "admin_token": admin_token,
    }), 200


# ─── İstatistikler ─────────────────────────────────────────────────────────────
@admin_bp.route("/stats", methods=["GET"])
@admin_required
def get_stats():
    """Admin paneli için genel istatistikleri döndürür."""
    total_tokens = Token.query.count()
    active_tokens = Token.query.filter_by(revoked=False).count()
    revoked_tokens = Token.query.filter_by(revoked=True).count()
    total_users = User.query.count()

    total_searches = db.session.query(db.func.sum(Token.usage_count)).scalar() or 0

    return jsonify({
        "total_tokens": total_tokens,
        "active_tokens": active_tokens,
        "revoked_tokens": revoked_tokens,
        "total_users": total_users,
        "total_searches": int(total_searches),
    })


# ─── Token Listeleme ──────────────────────────────────────────────────────────
@admin_bp.route("/tokens", methods=["GET"])
@admin_required
def list_tokens():
    """Tüm erişim token'larını listeler."""
    tokens = Token.query.order_by(Token.created_at.desc()).all()
    return jsonify([{
        "id":           t.id,
        "key":          t.key,
        "note":         t.note or "Not yok",
        "revoked":      t.revoked,
        "usage_count":  t.usage_count or 0,
        "created_at":   t.created_at.strftime("%d.%m.%Y %H:%M") if t.created_at else "-",
        "last_used_at": t.last_used_at.strftime("%d.%m.%Y %H:%M") if t.last_used_at else "Kullanılmadı",
    } for t in tokens])


# ─── Yeni Token Üret ──────────────────────────────────────────────────────────
@admin_bp.route("/tokens/generate", methods=["POST"])
@admin_required
def generate_token():
    """Yeni bir erişim token'ı üretir."""
    data = request.get_json(silent=True) or {}
    note = data.get("note", "").strip() or "Genel Kullanıcı"
    custom_key = data.get("custom_key", "").strip()

    if custom_key:
        exists = Token.query.filter_by(key=custom_key).first()
        if exists:
            return jsonify({"msg": "Bu anahtar zaten mevcut!"}), 409
        key = custom_key
    else:
        key = Token.generate_key()

    new_token = Token(
        key=key,
        note=note,
        revoked=False,
        usage_count=0,
    )
    db.session.add(new_token)
    db.session.commit()

    logger.info(f"Yeni token oluşturuldu: {key} ({note})")
    return jsonify({
        "msg": "Token başarıyla oluşturuldu",
        "token": {
            "id": new_token.id,
            "key": new_token.key,
            "note": new_token.note,
            "created_at": new_token.created_at.strftime("%d.%m.%Y %H:%M"),
        }
    }), 201


# ─── Token Durumunu Değiştir (İptal Et / Aktif Et) ────────────────────────────
@admin_bp.route("/tokens/<int:token_id>/toggle", methods=["POST"])
@admin_required
def toggle_token(token_id: int):
    """Token'ı iptal eder veya tekrar aktif hale getirir."""
    token = Token.query.get(token_id)
    if not token:
        return jsonify({"msg": "Token bulunamadı"}), 404

    token.revoked = not token.revoked
    db.session.commit()

    durum = "iptal edildi" if token.revoked else "aktif edildi"
    logger.info(f"Token durumu değişti: ID={token_id}, revoked={token.revoked}")
    return jsonify({
        "msg": f"Token başarıyla {durum}",
        "revoked": token.revoked,
    })


# ─── Token Sil ────────────────────────────────────────────────────────────────
@admin_bp.route("/tokens/<int:token_id>", methods=["DELETE"])
@admin_required
def delete_token(token_id: int):
    """Belirli bir token'ı veritabanından tamamen siler."""
    token = Token.query.get(token_id)
    if not token:
        return jsonify({"msg": "Token bulunamadı"}), 404

    db.session.delete(token)
    db.session.commit()
    logger.info(f"Token silindi: ID={token_id}")
    return jsonify({"msg": "Token başarıyla silindi"})


# ─── Sorgulanan Kullanıcılar ──────────────────────────────────────────────────
@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    """Sorgulanıp kaydedilen tüm Hazaclub kullanıcılarını listeler."""
    users = User.query.order_by(User.id.desc()).all()
    return jsonify([{
        "id":         u.id,
        "mid":        u.mid,
        "nick":       u.nick,
        "avatar":     u.avatar,
        "ip":         u.ip or "-",
        "device":     u.device or "-",
        "created_at": u.created_at.strftime("%d.%m.%Y %H:%M") if u.created_at else "-",
    } for u in users])


# ─── Kullanıcı Sil ────────────────────────────────────────────────────────────
@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id: int):
    """Sorgu geçmişinden bir kullanıcıyı siler."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Kullanıcı bulunamadı"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"msg": "Kullanıcı kaydı silindi"})
