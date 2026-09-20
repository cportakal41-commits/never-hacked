import time
import json
import logging
import os
from datetime import datetime, timedelta
import requests
from .. import db
from ..models import TreasureScanLog, RewardCooldown

logger = logging.getLogger(__name__)

HAZACLUB_TREASURE_URL = "https://api.hazaclub.com/treasure/get_grid_list"

# Hazaclub Tarayıcı Başlıkları (Android 4.7.0)
HAZACLUB_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://vueh5.hazaclub.com",
    "Referer": "https://vueh5.hazaclub.com/",
    "User-Agent": "Mozilla/5.0 (Linux; Android 9; SM-G970N Build/PQ3A.190605.06171433; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.82 Mobile Safari/537.36",
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

    # Tarama için aktif Hazaclub hesabı bilgileri: Önce veritabanından (Admin Paneli canlı ayarlarından) oku
    from ..models import SystemSetting
    db_scan_token = SystemSetting.get_setting("scan_token", "").strip()
    scan_token = db_scan_token if db_scan_token else os.environ.get("HAZACLUB_SCAN_TOKEN", "4I+vagAAAAA2uhkGAAAAAKfZSLF5R8KsAA==").strip()

    db_scan_mid = SystemSetting.get_setting("scan_mid", "").strip()
    mid_str = db_scan_mid if db_scan_mid else os.environ.get("HAZACLUB_SCAN_MID", "102349366").strip()
    try:
        scan_mid = int(mid_str)
    except ValueError:
        scan_mid = 102349366

    payload = {
        "offset": "1",
        "h_token": scan_token,
        "h_mid": scan_mid,
        "paddingTop": 24,
        "paddingBottom": 0,
        "h_app": 0,
        "h_av": "4.7.0",
        "h_dt": 1,
        "h_is_debug": 0,
        "h_lang": "tr",
        "h_os": "28",
        "h_did": "dcde917b8cddc8b6",
        "h_adid": "2bb2d3cc-626e-42da-a46f-3a4a6fad12c8",
        "h_ch": "GooglePlay",
        "h_nt": 4,
        "h_vpn": 1,
        "h_brand": "samsung",
        "h_model": "SM-G970N",
        "h_lbs_off": True,
        "h_sim": "TR",
        "h_h5plat": 1
    }

    found_items = []
    cooldown_suppressed = []
    rewards_to_cooldown = set()
    pages_scanned = 0
    api_error_msg = None

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
                if r.status_code == 401:
                    api_error_msg = "Hazaclub tarama tokeni geçersiz veya süresi dolmuş (HTTP 401)"
                else:
                    api_error_msg = f"Hazaclub API HTTP {r.status_code} hatası verdi"
                break

            data = r.json()
            if data.get("ret") != 1:
                logger.info(f"Hazaclub API ret != 1: {data.get('msg')} (Sayfa {pages_scanned})")
                api_error_msg = f"Hazaclub API hatası: {data.get('msg')}"
                break

            grid_list = data.get("data", {}).get("list", [])
            if not grid_list:
                break

            for item in grid_list:
                rid = item.get("reward_id")
                is_open = item.get("is_open", False)

                # Sadece hedef ödüller ve henüz açılmamış (is_open == False) olanlar
                if rid in TARGET_REWARDS and not is_open:
                    target_info = TARGET_REWARDS[rid]
                    item_data = {
                        "reward_id": rid,
                        "name": target_info["name"],
                        "icon": target_info["icon"],
                        "grid": item.get("id"),
                        "page": pages_scanned,
                        "is_open": is_open
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
        api_error_msg = f"Tarama bağlantı hatası: {str(e)}"

    # NOT: Tarama esnasında cooldown BAŞLATILMAZ! 
    # Cooldown yalnızca kullanıcı kutuyu başarıyla açıp ödülü aldığında (light_up) başlar.

    # Özet metni oluştur
    if found_items:
        counts = {}
        for itm in found_items:
            counts[itm["name"]] = counts.get(itm["name"], 0) + 1
        summary = ", ".join(f"{name} ({cnt})" for name, cnt in counts.items())
    elif cooldown_suppressed:
        summary = "Ödül haritada var ancak bekleme süresinde (cooldown)"
    elif api_error_msg:
        summary = api_error_msg
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
        "status": "success" if not api_error_msg or found_items else "error",
        "found_items": found_items,
        "cooldown_suppressed_count": len(cooldown_suppressed),
        "pages_scanned": pages_scanned,
        "summary": summary,
        "error_detail": api_error_msg,
        "cooldowns": updated_cooldowns
    }


HAZACLUB_LIGHTUP_URL = "https://api.hazaclub.com/treasure/light_up"

def send_light_up(grid_id: int, page_no: int, h_token: str, h_mid: int, app_token_key: str = None):
    """
    Hazaclub /treasure/light_up endpoint'ine ödül alma / ışık yakma isteği gönderir.
    """
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://vueh5.hazaclub.com",
        "Referer": "https://vueh5.hazaclub.com/",
        "sec-ch-ua": '"Chromium";v="124", "Android WebView";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Linux; Android 9; SM-G970N Build/PQ3A.190605.06171433; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/124.0.6367.82 Mobile Safari/537.36",
        "X-Requested-With": "com.tinytaala.chat"
    }

    payload = {
        "grid_id": int(grid_id),
        "page_no": int(page_no),
        "h_token": str(h_token).strip(),
        "h_mid": int(h_mid),
        "paddingTop": 24,
        "paddingBottom": 0,
        "h_app": 0,
        "h_av": "4.7.0",
        "h_dt": 1,
        "h_is_debug": 0,
        "h_lang": "tr",
        "h_os": "28",
        "h_did": "dcde917b8cddc8b6",
        "h_adid": "2bb2d3cc-626e-42da-a46f-3a4a6fad12c8",
        "h_ch": "GooglePlay",
        "h_nt": 4,
        "h_vpn": 1,
        "h_ts": int(time.time() * 1000),
        "h_brand": "samsung",
        "h_model": "SM-G970N",
        "h_lbs_off": True,
        "h_sim": "TR",
        "h_h5plat": 1
    }

    try:
        res = requests.post(HAZACLUB_LIGHTUP_URL, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            return {
                "status": "error",
                "ret": res.status_code,
                "msg": f"Hazaclub API HTTP {res.status_code} hatası verdi."
            }

        data = res.json()
        ret = data.get("ret")
        if ret == 1:
            show_rewards = data.get("data", {}).get("show_rewards", [])
            return {
                "status": "success",
                "ret": 1,
                "data": data.get("data", {}),
                "show_rewards": show_rewards,
                "msg": "Işık başarıyla yakıldı! Ödül hesabınıza gönderildi."
            }
        else:
            return {
                "status": "error",
                "ret": ret,
                "msg": data.get("msg") or "İşlem başarısız (Kutu daha önce açılmış veya token geçersiz olabilir).",
                "raw": data
            }
    except Exception as e:
        logger.error(f"Light-up isteğinde hata: {e}", exc_info=True)
        return {
            "status": "error",
            "ret": -1,
            "msg": f"Bağlantı hatası: {str(e)}"
        }
