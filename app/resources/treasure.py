import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.treasure_scanner import scan_treasure_grid, get_token_cooldown_status
from ..models import Token

logger = logging.getLogger(__name__)
treasure_bp = Blueprint("treasure", __name__)


def _get_current_token():
    """Mevcut JWT'den Token nesnesini bulur."""
    token_id = get_jwt_identity()
    try:
        token = Token.query.get(int(token_id))
        return token
    except Exception:
        return None


@treasure_bp.route("/treasure/status", methods=["GET"])
@jwt_required()
def get_status():
    """
    Kullanıcının 3 hedef ödül için mevcut bekleme süresi (cooldown) durumlarını döndürür.
    """
    token = _get_current_token()
    if not token:
        return jsonify({"msg": "Yetkisiz veya geçersiz token"}), 401

    cooldowns = get_token_cooldown_status(token.key)
    return jsonify({
        "token": token.key,
        "cooldowns": cooldowns
    })


@treasure_bp.route("/treasure/scan", methods=["POST"])
@jwt_required()
def run_scan():
    """
    Hazine tarama motorunu çalıştırır.
    Sadece PRİNCE (3 gün bekleme), HAZA HUNTER (1 gün bekleme) ve EFSANE ÇERÇEVE (1 gün bekleme)
    ödüllerini arar ve sonuçları döndürür.
    """
    token = _get_current_token()
    if not token:
        return jsonify({"msg": "Yetkisiz veya geçersiz token"}), 401

    if token.revoked:
        return jsonify({"msg": "Bu token admin tarafından iptal edilmiştir!"}), 403

    logger.info(f"Hazine taraması başlatıldı – Token={token.key} ({token.note})")

    result = scan_treasure_grid(
        token_key=token.key,
        token_note=token.note or "Genel Kullanıcı"
    )

    return jsonify(result)
