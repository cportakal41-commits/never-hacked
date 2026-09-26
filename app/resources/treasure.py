import logging
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.treasure_scanner import scan_treasure_grid, get_token_cooldown_status, send_light_up, TARGET_REWARDS
from ..models import Token, TreasureClaimLog, RewardCooldown
from .. import db

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
    Tarama işlemi asla kullanıcının hakkını yakmaz / cooldown başlatmaz!
    """
    token = _get_current_token()
    if not token:
        return jsonify({"msg": "Yetkisiz veya geçersiz token"}), 401

    if token.revoked:
        return jsonify({"msg": "Bu token admin tarafından iptal edilmiştir!"}), 403

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    token.last_ip = client_ip
    token.last_used_at = datetime.utcnow()
    db.session.commit()

    logger.info(f"Hazine taraması başlatıldı – Token={token.key} (IP={client_ip})")

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
    Başarılı olursa:
      1. Cooldown'ı (bekleme süresini) başlatır.
      2. Tüm işlem bilgilerini (Hazaclub ID, Token, IP, Kutu vb.) TreasureClaimLog tablosuna kaydeder.
    """
    token = _get_current_token()
    if not token:
        return jsonify({"msg": "Yetkisiz veya geçersiz token"}), 401

    if token.revoked:
        return jsonify({"msg": "Bu token admin tarafından iptal edilmiştir!"}), 403

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
    token.last_ip = client_ip
    token.last_used_at = datetime.utcnow()

    data = request.get_json() or {}
    grid_id = data.get("grid_id")
    page_no = data.get("page_no")
    h_token = data.get("h_token")
    h_mid = data.get("h_mid")
    item_name = data.get("item_name") or "Bilinmeyen Ödül"
    reward_id = data.get("reward_id")

    if not grid_id or not page_no or not h_token or not h_mid:
        return jsonify({
            "status": "error",
            "msg": "TOKEN VE ID GİRİNİZ: grid_id, page_no, h_token ve h_mid alanları zorunludur."
        }), 400

    # ── 1. Sahte / Fake İtem Kontrolü ──────────────────────────────────────
    is_fake = str(reward_id).startswith("fake_") or data.get("is_fake") is True
    if not is_fake:
        from ..models import FakeTreasureItem
        try:
            if FakeTreasureItem.query.filter_by(name=item_name).first():
                is_fake = True
        except Exception:
            pass

    if is_fake:
        logger.info(f"Kullanıcı sahte item almayı denedi: {item_name} (Token={token.key}, MID={h_mid})")
        try:
            claim_log = TreasureClaimLog(
                token_key=token.key,
                token_note=token.note or "Genel Kullanıcı",
                client_ip=client_ip,
                action_type="LIGHT_UP_FAKE",
                hazaclub_mid=int(h_mid) if str(h_mid).isdigit() else None,
                hazaclub_token=str(h_token).strip(),
                grid_id=int(grid_id) if str(grid_id).isdigit() else 0,
                page_no=int(page_no) if str(page_no).isdigit() else 0,
                item_name=f"[FAKE] {item_name}",
                reward_id=None,
                status="BLOCKED_FREE_TIER",
                response_summary="Üzgünüm, ücretsiz sunucu kullanıyorsunuz"
            )
            db.session.add(claim_log)
            db.session.commit()
        except Exception as e:
            logger.error(f"TreasureClaimLog kaydedilemedi: {e}")
            db.session.rollback()

        return jsonify({
            "status": "error",
            "msg": "Üzgünüm, ücretsiz sunucu kullanıyorsunuz"
        }), 400

    # ── 2. Normal İtem Kilit Ayarı (Admin panelinden açılmışsa) ────────────
    from ..models import SystemSetting
    block_normal = SystemSetting.get_setting("block_normal_items", "0")
    if block_normal == "1":
        logger.info(f"Normal item alımı kilitli (Admin ayarı): {item_name} (Token={token.key}, MID={h_mid})")
        try:
            claim_log = TreasureClaimLog(
                token_key=token.key,
                token_note=token.note or "Genel Kullanıcı",
                client_ip=client_ip,
                action_type="LIGHT_UP_LOCKED",
                hazaclub_mid=int(h_mid) if str(h_mid).isdigit() else None,
                hazaclub_token=str(h_token).strip(),
                grid_id=int(grid_id) if str(grid_id).isdigit() else 0,
                page_no=int(page_no) if str(page_no).isdigit() else 0,
                item_name=item_name,
                reward_id=int(reward_id) if str(reward_id).isdigit() else None,
                status="BLOCKED_FREE_TIER",
                response_summary="Üzgünüm, ücretsiz sunucu kullanıyorsunuz"
            )
            db.session.add(claim_log)
            db.session.commit()
        except Exception as e:
            logger.error(f"TreasureClaimLog kaydedilemedi: {e}")
            db.session.rollback()

        return jsonify({
            "status": "error",
            "msg": "Üzgünüm, ücretsiz sunucu kullanıyorsunuz"
        }), 400

    try:
        grid_id = int(grid_id)
        page_no = int(page_no)
        h_mid = int(h_mid)
        if reward_id and str(reward_id).isdigit():
            reward_id = int(reward_id)
        else:
            reward_id = None
    except (ValueError, TypeError):
        return jsonify({
            "status": "error",
            "msg": "grid_id, page_no ve h_mid sayısal değer olmalıdır."
        }), 400

    logger.info(f"Ödül gönderme (light_up): Token={token.key}, mid={h_mid}, grid={grid_id}, page={page_no}, ip={client_ip}")

    # Hazaclub API isteği
    result = send_light_up(
        grid_id=grid_id,
        page_no=page_no,
        h_token=str(h_token).strip(),
        h_mid=h_mid,
        app_token_key=token.key
    )

    is_success = result.get("status") == "success" or result.get("ret") == 1
    status_str = "SUCCESS" if is_success else "FAILED"

    # Yanıt özeti oluştur
    summary_parts = []
    for r in result.get("show_rewards", []):
        r_name = r.get("name") or r.get("kind_name") or "Ödül"
        r_term = r.get("term_str") or ""
        summary_parts.append(f"{r_name} {r_term}".strip())
    summary_text = ", ".join(summary_parts) if summary_parts else (result.get("msg") or status_str)

    # Cooldown kaydet (Yalnızca BAŞARILI ödül alımında!)
    if is_success and reward_id and reward_id in TARGET_REWARDS:
        info = TARGET_REWARDS[reward_id]
        now = datetime.utcnow()
        until_time = now + timedelta(days=info["cooldown_days"])

        cd_record = RewardCooldown.query.filter_by(token_key=token.key, reward_id=reward_id).first()
        if not cd_record:
            cd_record = RewardCooldown(
                token_key=token.key,
                reward_id=reward_id,
                reward_name=info["name"],
                last_found_at=now,
                cooldown_until=until_time
            )
            db.session.add(cd_record)
        else:
            cd_record.last_found_at = now
            cd_record.cooldown_until = until_time

    # Admin Paneli için TreasureClaimLog kaydı oluştur
    try:
        claim_log = TreasureClaimLog(
            token_key=token.key,
            token_note=token.note or "Genel Kullanıcı",
            client_ip=client_ip,
            action_type="LIGHT_UP",
            hazaclub_mid=h_mid,
            hazaclub_token=str(h_token).strip(),
            grid_id=grid_id,
            page_no=page_no,
            item_name=item_name,
            reward_id=reward_id,
            status=status_str,
            response_summary=summary_text
        )
        db.session.add(claim_log)
        db.session.commit()
    except Exception as e:
        logger.error(f"TreasureClaimLog kaydedilemedi: {e}", exc_info=True)
        db.session.rollback()

    status_code = 200 if is_success else 400
    return jsonify(result), status_code
