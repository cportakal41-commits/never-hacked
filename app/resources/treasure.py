import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.treasure_scanner import scan_treasure_grid, get_token_cooldown_status, send_light_up
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
    Kullanıcının 3 hedef ödül için mevcut bekleme süresi durumlarını döndürür.
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
    Sadece PRINCE, HAZA HUNTER ve EFSANE ÇERÇEVE ödüllerini arar ve sonuçları döndürür.
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


@treasure_bp.route("/treasure/light-up", methods=["POST"])
@jwt_required()
def run_light_up():
    """
    Bulunan bir kutuyu açar / ışık yakar ve ödülü gönderir.
    Parametreler: grid_id, page_no, h_token, h_mid
    """
    token = _get_current_token()
    if not token:
        return jsonify({"msg": "Yetkisiz veya geçersiz token"}), 401

    if token.revoked:
        return jsonify({"msg": "Bu token admin tarafından iptal edilmiştir!"}), 403

    data = request.get_json() or {}
    grid_id = data.get("grid_id")
    page_no = data.get("page_no")
    h_token = data.get("h_token")
    h_mid = data.get("h_mid")

    if not grid_id or not page_no or not h_token or not h_mid:
        return jsonify({
            "status": "error",
            "msg": "TOKEN VE ID GİRİNİZ: grid_id, page_no, h_token ve h_mid alanları zorunludur."
        }), 400

    try:
        grid_id = int(grid_id)
        page_no = int(page_no)
        h_mid = int(h_mid)
    except (ValueError, TypeError):
        return jsonify({
            "status": "error",
            "msg": "grid_id, page_no ve h_mid sayısal değer olmalıdır."
        }), 400

    logger.info(f"Ödül gönderme (light_up) isteği: Token={token.key}, mid={h_mid}, grid={grid_id}, page={page_no}")

    result = send_light_up(
        grid_id=grid_id,
        page_no=page_no,
        h_token=str(h_token).strip(),
        h_mid=h_mid,
        app_token_key=token.key
    )

    status_code = 200 if result.get("status") == "success" else 400
    return jsonify(result), status_code
