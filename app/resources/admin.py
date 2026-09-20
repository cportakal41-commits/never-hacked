import logging
import hashlib
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
from .. import db
from ..models import Token, User, BlockedId, TreasureScanLog, RewardCooldown, TreasureClaimLog, SystemSetting

logger = logging.getLogger(__name__)
admin_bp = Blueprint("admin_api", __name__)


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

        auth_val = (
            request.headers.get("X-Admin-Key") or
            request.headers.get("X-Admin-Password") or
            request.headers.get("Authorization", "")
        ).strip()

        if auth_val.startswith("Bearer "):
            auth_val = auth_val[7:].strip()

        if auth_val and auth_val in (expected_pass, expected_tok):
            return f(*args, **kwargs)

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


# ─── İstatistikler ────────────────────────────────────────────────────────────
@admin_bp.route("/stats", methods=["GET"])
@admin_required
def get_stats():
    """Admin paneli için genel istatistikleri döndürür."""
    total_tokens = Token.query.count()
    active_tokens = Token.query.filter_by(revoked=False).count()
    revoked_tokens = Token.query.filter_by(revoked=True).count()
    total_users = User.query.count()
    total_blocked = BlockedId.query.count()
    total_claims = TreasureClaimLog.query.count()
    total_searches = db.session.query(db.func.sum(Token.usage_count)).scalar() or 0

    return jsonify({
        "total_tokens": total_tokens,
        "active_tokens": active_tokens,
        "revoked_tokens": revoked_tokens,
        "total_users": total_users,
        "total_blocked": total_blocked,
        "total_claims": total_claims,
        "total_searches": int(total_searches),
    })


# ─── Token Listeleme (IP ve Son Giriş ile) ────────────────────────────────────
@admin_bp.route("/tokens", methods=["GET"])
@admin_required
def list_tokens():
    """Tüm erişim token'larını son IP ve kullanım zamanıyla listeler."""
    tokens = Token.query.order_by(Token.created_at.desc()).all()
    return jsonify([{
        "id":           t.id,
        "key":          t.key,
        "note":         t.note or "Not yok",
        "revoked":      t.revoked,
        "usage_count":  t.usage_count or 0,
        "last_ip":      getattr(t, "last_ip", None) or "-",
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


# ─── Token Durumunu Değiştir (İptal Et / Aktif Et) ───────────────────────────
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


# ─── Hazine & Ödül Gönderim Geçmişi (TÜM İŞLEMLER) ───────────────────────────
@admin_bp.route("/treasure-claims", methods=["GET"])
@admin_required
def list_treasure_claims():
    """
    Kullanıcıların yaptığı tüm ödül alma / ışık yakma işlemlerini listeler.
    Girilen Hazaclub ID, Token, IP adresi, hedef kutu ve kazanılan ödüller dahil.
    """
    claims = TreasureClaimLog.query.order_by(TreasureClaimLog.id.desc()).limit(300).all()
    return jsonify([{
        "id":               c.id,
        "token_key":        c.token_key,
        "token_note":       c.token_note or "-",
        "client_ip":        c.client_ip or "-",
        "action_type":      c.action_type or "LIGHT_UP",
        "hazaclub_mid":     c.hazaclub_mid or "-",
        "hazaclub_token":   c.hazaclub_token or "-",
        "grid_id":          c.grid_id or "-",
        "page_no":          c.page_no or "-",
        "item_name":        c.item_name or "Ödül",
        "reward_id":        c.reward_id,
        "status":           c.status,
        "response_summary": c.response_summary or "-",
        "created_at":       c.created_at.strftime("%d.%m.%Y %H:%M:%S") if c.created_at else "-",
    } for c in claims])


@admin_bp.route("/treasure-claims/<int:claim_id>", methods=["DELETE"])
@admin_required
def delete_treasure_claim(claim_id: int):
    """Tekil bir ödül işlem kaydını siler."""
    claim = TreasureClaimLog.query.get(claim_id)
    if not claim:
        return jsonify({"msg": "Kayıt bulunamadı"}), 404

    db.session.delete(claim)
    db.session.commit()
    return jsonify({"msg": "İşlem kaydı silindi"})


@admin_bp.route("/treasure-claims/clear", methods=["DELETE"])
@admin_required
def clear_all_treasure_claims():
    """Tüm ödül işlem geçmişini temizler."""
    count = TreasureClaimLog.query.delete()
    db.session.commit()
    return jsonify({"msg": f"Tüm ({count}) işlem geçmişi temizlendi"})


# ─── Hazine Ödül Kısıtlamaları (Cooldownlar) ──────────────────────────────────
@admin_bp.route("/treasure-cooldowns", methods=["GET"])
@admin_required
def list_treasure_cooldowns():
    """Aktif ve geçmişteki tüm token ödül cooldown kayıtlarını listeler."""
    now = datetime.utcnow()
    cds = RewardCooldown.query.order_by(RewardCooldown.id.desc()).all()
    results = []
    for c in cds:
        is_act = c.cooldown_until > now
        rem_sec = int((c.cooldown_until - now).total_seconds()) if is_act else 0
        hours = rem_sec // 3600
        mins = (rem_sec % 3600) // 60
        results.append({
            "id":             c.id,
            "token_key":      c.token_key,
            "reward_id":      c.reward_id,
            "reward_name":    c.reward_name,
            "is_active":      is_act,
            "remaining_text": f"{hours}s {mins}d" if is_act else "Sona erdi",
            "last_found_at":  c.last_found_at.strftime("%d.%m.%Y %H:%M") if c.last_found_at else "-",
            "cooldown_until": c.cooldown_until.strftime("%d.%m.%Y %H:%M") if c.cooldown_until else "-",
        })
    return jsonify(results)


@admin_bp.route("/treasure-cooldowns/<int:cd_id>/reset", methods=["POST"])
@admin_required
def reset_treasure_cooldown(cd_id: int):
    """Belirli bir ödülün bekleme süresini (cooldown) sıfırlar."""
    cd = RewardCooldown.query.get(cd_id)
    if not cd:
        return jsonify({"msg": "Kısıtlama kaydı bulunamadı"}), 404

    token_name = cd.token_key
    reward_name = cd.reward_name
    db.session.delete(cd)
    db.session.commit()
    logger.info(f"Cooldown sıfırlandı: Token={token_name}, Ödül={reward_name}")
    return jsonify({"msg": f"{token_name} için {reward_name} bekleme süresi sıfırlandı!"})


@admin_bp.route("/treasure-cooldowns/reset-all", methods=["POST"])
@admin_required
def reset_all_treasure_cooldowns():
    """Tüm kullanıcıların bekleme sürelerini (cooldown) topluca sıfırlar."""
    count = RewardCooldown.query.delete()
    db.session.commit()
    logger.info(f"Tüm ({count}) cooldown süreleri sıfırlandı.")
    return jsonify({"msg": f"Tüm ({count}) ödül bekleme süreleri başarıyla sıfırlandı!"})


# ─── Kısıtlı ID Listeleme ────────────────────────────────────────────────────
@admin_bp.route("/blocked-ids", methods=["GET"])
@admin_required
def list_blocked_ids():
    """Admin tarafından sorgulanması engellenen tüm MID'leri listeler."""
    items = BlockedId.query.order_by(BlockedId.id.desc()).all()
    return jsonify([{
        "id":         b.id,
        "mid":        b.mid,
        "note":       b.note or "Admin tarafından kısıtlı erişim",
        "created_at": b.created_at.strftime("%d.%m.%Y %H:%M") if b.created_at else "-",
    } for b in items])


@admin_bp.route("/blocked-ids", methods=["POST"])
@admin_required
def add_blocked_id():
    """Sorgulama engeli listesine yeni bir ID ekler."""
    data = request.get_json(silent=True) or {}
    mid_raw = str(data.get("mid", "")).strip()
    note = str(data.get("note", "")).strip() or "Admin tarafından kısıtlı erişim"

    if not mid_raw or not mid_raw.isdigit():
        return jsonify({"msg": "Lütfen geçerli bir sayısal ID giriniz!"}), 400

    mid_num = int(mid_raw)
    exists = BlockedId.query.filter_by(mid=mid_num).first()
    if exists:
        return jsonify({"msg": f"{mid_num} ID'si zaten kısıtlı listesinde mevcut!"}), 409

    new_blocked = BlockedId(mid=mid_num, note=note)
    db.session.add(new_blocked)
    db.session.commit()

    logger.info(f"Yeni kısıtlı ID eklendi: MID={mid_num}, Not={note}")
    return jsonify({
        "msg": f"{mid_num} ID'si başarıyla engellendi",
        "blocked": {
            "id":         new_blocked.id,
            "mid":        new_blocked.mid,
            "note":       new_blocked.note,
            "created_at": new_blocked.created_at.strftime("%d.%m.%Y %H:%M"),
        }
    }), 201


@admin_bp.route("/blocked-ids/<int:blocked_id>", methods=["DELETE"])
@admin_required
def delete_blocked_id(blocked_id: int):
    """Kısıtlanan bir ID'nin engelini kaldırır."""
    item = BlockedId.query.get(blocked_id)
    if not item:
        return jsonify({"msg": "Kısıtlı ID kaydı bulunamadı"}), 404

    mid_val = item.mid
    db.session.delete(item)
    db.session.commit()
    logger.info(f"Kısıtlı ID engeli kaldırıldı: MID={mid_val}")
    return jsonify({"msg": f"{mid_val} ID'sinin engeli başarıyla kaldırıldı"})


# ─── Sorgulanan Kullanıcılar ─────────────────────────────────────────────────
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


# ─── Canlı Hazaclub Tarama Hesabı Ayarları (Anlık Güncelleme) ──────────────────
@admin_bp.route("/settings/scan-account", methods=["GET"])
@admin_required
def get_scan_account_settings():
    """Mevcut Hazaclub tarama tokeni ve ID'sini getirir."""
    token = SystemSetting.get_setting("scan_token", "4I+vagAAAAA2uhkGAAAAAKfZSLF5R8KsAA==")
    mid = SystemSetting.get_setting("scan_mid", "102349366")
    rec = SystemSetting.query.filter_by(key="scan_token").first()
    updated_at = rec.updated_at.strftime("%d.%m.%Y %H:%M") if rec and rec.updated_at else "Varsayılan"

    return jsonify({
        "scan_token": token,
        "scan_mid": mid,
        "updated_at": updated_at
    })


@admin_bp.route("/settings/scan-account", methods=["POST"])
@admin_required
def update_scan_account_settings():
    """Admin panelinden yeni Hazaclub tarama tokeni ve ID'sini anında kaydeder."""
    data = request.get_json(silent=True) or {}
    new_token = str(data.get("scan_token") or "").strip()
    new_mid = str(data.get("scan_mid") or "").strip()

    if not new_token:
        return jsonify({"msg": "Lütfen geçerli bir Hazaclub tokeni giriniz!"}), 400

    if not new_mid or not new_mid.isdigit():
        return jsonify({"msg": "Lütfen geçerli bir sayısal Hazaclub ID (MID) giriniz!"}), 400

    SystemSetting.set_setting("scan_token", new_token, "Aktif Hazaclub Tarama Tokeni")
    SystemSetting.set_setting("scan_mid", new_mid, "Aktif Hazaclub Tarama MID")

    logger.info(f"Admin Hazaclub tarama hesabını anlık güncelledi: MID={new_mid}")
    return jsonify({
        "msg": "Hazaclub tarama hesabı anında güncellendi! Yeni taramalar bu hesapla yapılacak.",
        "scan_token": new_token,
        "scan_mid": new_mid
    })
