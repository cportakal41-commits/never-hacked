import time
import json
import logging
from datetime import datetime, timedelta
import requests
from .. import db
from ..models import TreasureScanLog, RewardCooldown

logger = logging.getLogger(__name__)

HAZACLUB_TREASURE_URL = "https://api.hazaclub.com/treasure/get_grid_list"

HAZACLUB_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://vueh5.hazaclub.com",
    "Referer": "https://vueh5.hazaclub.com/",
    "User-Agent": "Mozilla/5.0 (Linux; Android 9; NE2211 Build/SKQ1.220617.001; wv) AppleWebKit/537.36",
    "X-Requested-With": "com.tinytaala.chat"
}

# 🎯 İstenen 3 Hedef Ödül ve Bekleme Süreleri (Cooldown)
TARGET_REWARDS = {
    2373: {
        "name": "PRİNCE",
        "cooldown_days": 3,
        "badge_color": "#ffd700",
        "icon": "👑"
    },
    659334: {
        "name": "HAZA HUNTER",
        "cooldown_days": 1,
        "badge_color": "#00ff66",
        "icon": "🏹"
    },
    6: {
        "name": "EFSANE ÇERÇEVE",
        "cooldown_days": 1,
        "badge_color": "#a855f7",
        "icon": "🖼️"
    }
}


def get_token_cooldown_status(token_key: str):
    """
    Belirli bir token için 3 hedef ödülün aktif bekleme (cooldown) durumlarını döndürür.
    """
    now = datetime.utcnow()
    result = []

    cooldown_records = {
        c.reward_id: c
        for c in RewardCooldown.query.filter_by(token_key=token_key).all()
    }

    for rid, info in TARGET_REWARDS.items():
        rec = cooldown_records.get(rid)
        if rec and rec.cooldown_until > now:
            remaining = int((rec.cooldown_until - now).total_seconds())
            hours = remaining // 3600
            mins = (remaining % 3600) // 60
            result.append({
                "reward_id": rid,
                "name": info["name"],
                "icon": info["icon"],
                "cooldown_days": info["cooldown_days"],
                "is_ready": False,
                "remaining_seconds": remaining,
                "remaining_text": f"{hours}s {mins}d",
                "next_available_at": rec.cooldown_until.strftime("%d.%m.%Y %H:%M")
            })
        else:
            result.append({
                "reward_id": rid,
                "name": info["name"],
                "icon": info["icon"],
                "cooldown_days": info["cooldown_days"],
                "is_ready": True,
                "remaining_seconds": 0,
                "remaining_text": "Hazır",
                "next_available_at": "Hemen"
            })

    return result


def scan_treasure_grid(token_key: str, token_note: str = "Genel Kullanıcı"):
    """
    Hazaclub hazine ızgarasını (max 50 sayfa) tarar.
    Sadece PRİNCE, HAZA HUNTER ve EFSANE ÇERÇEVE ödüllerini filtreler.
    Kullanıcının cooldown sürelerini kontrol eder ve uygular.
    Taramayı veritabanına loglar.
    """
    now = datetime.utcnow()

    # Mevcut aktif cooldown'ları al
    active_cooldowns = {
        c.reward_id: c.cooldown_until
        for c in RewardCooldown.query.filter_by(token_key=token_key).all()
        if c.cooldown_until > now
    }

    payload = {
        "offset": "1",
        "h_token": "G32vagAAAACTShEGAAAAAJiLeIjnTvgWAA==",
        "h_mid": 101796499,
        "paddingTop": 24,
        "paddingBottom": 0,
        "h_app": 0,
        "h_av": "3.7.0",
        "h_dt": 1,
        "h_is_debug": 0,
        "h_lang": "tr",
        "h_os": "28",
        "h_did": "951aa291e2d38e4a",
        "h_adid": "d03a782e-8065-4a5d-a628-0ba703276b43",
        "h_ch": "GooglePlay",
        "h_nt": 1,
        "h_brand": "OnePlus",
        "h_model": "NE2211",
        "h_lbs_off": True,
        "h_sim": "tr"
    }

    found_items = []
    cooldown_suppressed = []
    rewards_to_cooldown = set()
    pages_scanned = 0

    try:
        for i in range(50):
            payload["h_ts"] = int(time.time() * 1000)
            pages_scanned = i + 1

            r = requests.post(
                HAZACLUB_TREASURE_URL,
                json=payload,
                headers=HAZACLUB_HEADERS,
                timeout=12
            )
            if r.status_code != 200:
                logger.warning(f"Hazaclub API HTTP {r.status_code} döndü (Sayfa {pages_scanned})")
                break

            data = r.json()
            if data.get("ret") != 1:
                logger.info(f"Hazaclub API ret != 1: {data.get('msg')} (Sayfa {pages_scanned})")
                break

            grid_list = data.get("data", {}).get("list", [])
            if not grid_list:
                break

            for item in grid_list:
                rid = item.get("reward_id")
                if rid in TARGET_REWARDS:
                    target_info = TARGET_REWARDS[rid]
                    item_data = {
                        "reward_id": rid,
                        "name": target_info["name"],
                        "icon": target_info["icon"],
                        "grid": item.get("id"),
                        "page": pages_scanned
                    }

                    # Cooldown kontrolü: Bu ödül şu an bu token için beklemede mi?
                    if rid in active_cooldowns:
                        cooldown_suppressed.append(item_data)
                    else:
                        found_items.append(item_data)
                        rewards_to_cooldown.add(rid)

            next_offset = data.get("data", {}).get("offset")
            if not next_offset or next_offset == payload.get("offset"):
                break
            payload["offset"] = next_offset

    except Exception as e:
        logger.error(f"Tarama sırasında hata oluştu: {e}", exc_info=True)

    # Yeni bulunan ödüller için cooldown sürelerini veritabanında başlat / güncelle
    for rid in rewards_to_cooldown:
        info = TARGET_REWARDS[rid]
        until_time = now + timedelta(days=info["cooldown_days"])

        cd_record = RewardCooldown.query.filter_by(token_key=token_key, reward_id=rid).first()
        if not cd_record:
            cd_record = RewardCooldown(
                token_key=token_key,
                reward_id=rid,
                reward_name=info["name"],
                last_found_at=now,
                cooldown_until=until_time
            )
            db.session.add(cd_record)
        else:
            cd_record.last_found_at = now
            cd_record.cooldown_until = until_time

    # Özet metni oluştur
    if found_items:
        counts = {}
        for itm in found_items:
            counts[itm["name"]] = counts.get(itm["name"], 0) + 1
        summary = ", ".join(f"{name} ({cnt})" for name, cnt in counts.items())
    elif cooldown_suppressed:
        summary = "Ödül haritada var ancak bekleme süresinde (cooldown)"
    else:
        summary = "Hedef ödül bulunamadı"

    # Tarama logunu veritabanına kaydet
    try:
        scan_log = TreasureScanLog(
            token_key=token_key,
            token_note=token_note or "Genel Kullanıcı",
            found_summary=summary,
            raw_results=json.dumps(found_items, ensure_ascii=False),
            pages_scanned=pages_scanned
        )
        db.session.add(scan_log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Tarama logu kaydedilemedi: {e}")
        db.session.rollback()

    updated_cooldowns = get_token_cooldown_status(token_key)

    return {
        "status": "success",
        "found_items": found_items,
        "cooldown_suppressed_count": len(cooldown_suppressed),
        "pages_scanned": pages_scanned,
        "summary": summary,
        "cooldowns": updated_cooldowns
    }
