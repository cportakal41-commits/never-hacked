import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.hazaclub import get_user_data
from .. import db
from ..models import User, Token, BlockedId

logger = logging.getLogger(__name__)
search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["GET"])
@jwt_required()
def search():
    """
    MID'e göre kullanıcı arama endpoint'i.
    JWT token zorunludur. Hazaclub API'ından anlık veri çeker ve veritabanına kaydeder.
    """
    mid = request.args.get("mid", "").strip()

    if not mid or not mid.isdigit():
        return jsonify({"msg": "Geçersiz MID – yalnızca sayısal değer kabul edilir"}), 400

    mid_num = int(mid)

    # Admin tarafından engellenen kısıtlı ID kontrolü
    blocked = BlockedId.query.filter_by(mid=mid_num).first()
    if blocked:
        logger.warning(f"Kısıtlı ID sorgulanmaya çalışıldı – MID={mid_num}")
        return jsonify({"msg": blocked.note or "Admin tarafından kısıtlı erişim"}), 403

    logger.info(f"Arama yapılıyor – MID={mid_num}")
    data = get_user_data(mid_num)

    if not data:
        return jsonify({"msg": "Kullanıcı bulunamadı"}), 404

    # Token kullanım istatistiğini artır
    try:
        token_id = int(get_jwt_identity())
        token_record = Token.query.get(token_id)
        if token_record:
            token_record.usage_count = (token_record.usage_count or 0) + 1
            token_record.last_used_at = db.func.now()
    except Exception as e:
        logger.warning(f"Token kullanım sayacı güncellenemedi: {e}")

    # Veritabanına kaydet / güncelle (Admin panelinde listelenmesi için)
    try:
        user = User.query.filter_by(mid=mid_num).first()
        if not user:
            user = User(
                mid=mid_num,
                nick=data.get("nick") or "Bilinmiyor",
                avatar=data.get("avatar"),
                ip=data.get("ip"),
                device=data.get("login_device"),
                os=data.get("os_ver"),
            )
            db.session.add(user)
        else:
            user.nick = data.get("nick") or user.nick
            user.avatar = data.get("avatar") or user.avatar
            user.ip = data.get("ip") or user.ip
            user.device = data.get("login_device") or user.device
            user.os = data.get("os_ver") or user.os
        db.session.commit()
    except Exception as e:
        logger.error(f"Kullanıcı kaydedilirken hata: {e}")
        db.session.rollback()

    return jsonify({
        "mid":    data.get("mid"),
        "nick":   data.get("nick"),
        "avatar": data.get("avatar"),
        "ip":     data.get("ip"),
        "device": data.get("login_device"),
    })
