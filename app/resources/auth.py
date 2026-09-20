import logging
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.hazaclub import get_user_data
from ..services.token_manager import create_token, create_token_for_key
from .. import db
from ..models import User, Token

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Token anahtarı ile giriş endpoint'i.
    Admin panelinden üretilen Token (örn: NH-XXXX-XXXX) ile giriş yapılır.

    İstek gövdesi: {"token": "NH-DEMO-2026-KEY"} veya {"key": "..."}
    """
    data = request.get_json(silent=True) or {}
    key = data.get("token") or data.get("key")

    if not key or not str(key).strip():
        return jsonify({"msg": "Lütfen bir erişim token'ı giriniz."}), 400

    key = str(key).strip()

    token_record = Token.query.filter_by(key=key).first()
    if not token_record:
        return jsonify({"msg": "Geçersiz erişim token'ı! Lütfen admin panelinden geçerli bir token alın."}), 401

    if token_record.revoked:
        return jsonify({"msg": "Bu token admin tarafından iptal edilmiştir!"}), 403

    # Kullanım sayısını ve tarihini güncelle
    token_record.usage_count = (token_record.usage_count or 0) + 1
    token_record.last_used_at = datetime.utcnow()
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    token_record.last_ip = client_ip
    db.session.commit()

    # JWT oluştur
    access_token = create_token_for_key(token_record)

    return jsonify({
        "access_token": access_token,
        "key": token_record.key,
        "note": token_record.note,
    }), 200

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """Mevcut oturumdaki token bilgilerini döndürür."""
    token_id = int(get_jwt_identity())
    token = Token.query.get(token_id)
    if not token or token.revoked:
        return jsonify({"msg": "Token geçersiz veya iptal edilmiş"}), 401

    return jsonify({
        "key": token.key,
        "note": token.note,
        "usage_count": token.usage_count,
        "created_at": str(token.created_at),
    })


@auth_bp.route("/logout", methods=["DELETE"])
@jwt_required()
def logout():
    """
    Mevcut token'ı geçersiz kılar (blocklist'e ekler).
    Çıkış işlemi sunucu taraflı token revokasyonu ile gerçekleşir.
    """
    from flask_jwt_extended import get_jwt
    from ..models import Token

    jti = get_jwt()["jti"]
    token = Token.query.filter_by(jti=jti).first()
    if token:
        token.revoked = True
        db.session.commit()
        logger.info(f"Token revoke edildi (logout) – jti={jti[:8]}...")

    return jsonify({"msg": "Başarıyla çıkış yapıldı"}), 200
