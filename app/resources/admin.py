import logging
from flask import Blueprint, request, jsonify
from datetime import datetime
from .. import db
from ..models import Token, User

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin_api", __name__)


# ─── İstatistikler ─────────────────────────────────────────────────────────────
@admin_bp.route("/stats", methods=["GET"])
def get_stats():
    """Admin paneli için genel istatistikleri döndürür."""
    total_tokens = Token.query.count()
    active_tokens = Token.query.filter_by(revoked=False).count()
    revoked_tokens = Token.query.filter_by(revoked=True).count()
    total_users = User.query.count()

    # Toplam yapılan arama sayısı (tüm token'ların usage_count toplamı)
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
def generate_token():
    """Yeni bir erişim token'ı üretir."""
    data = request.get_json(silent=True) or {}
    note = data.get("note", "").strip() or "Genel Kullanıcı"
    custom_key = data.get("custom_key", "").strip()

    # Özel anahtar belirtilmişse kontrol et
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
def delete_user(user_id: int):
    """Sorgu geçmişinden bir kullanıcıyı siler."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "Kullanıcı bulunamadı"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"msg": "Kullanıcı kaydı silindi"})
