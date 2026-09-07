import requests
import json
import logging

logger = logging.getLogger(__name__)

# Hazaclub paylaşım sayfası API endpoint'i
API_URL = "https://api.hazaclub.com/user/share_page"

# İsteğe eklenen başlıklar – gerçek bir tarayıcıyı taklit eder
HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://h5.hazaclub.com/",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
}


def get_user_data(mid: int) -> dict | None:
    """
    Hazaclub API'ından kullanıcı verilerini getirir.

    Args:
        mid: Hazaclub üye kimlik numarası

    Returns:
        Kullanıcı veri sözlüğü veya hata durumunda None
    """
    payload = {"mid": int(mid)}

    try:
        r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=15)
        r.raise_for_status()
    except requests.Timeout:
        logger.error(f"Hazaclub API zaman aşımı – MID: {mid}")
        return None
    except requests.ConnectionError:
        logger.error(f"Hazaclub API bağlantı hatası – MID: {mid}")
        return None
    except requests.HTTPError as exc:
        logger.error(f"Hazaclub API HTTP hatası {exc.response.status_code} – MID: {mid}")
        return None
    except requests.RequestException as exc:
        logger.error(f"Hazaclub API bilinmeyen hata – MID: {mid}: {exc}")
        return None

    try:
        data = r.json()
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"Geçersiz JSON yanıtı – MID: {mid}")
        return None

    # API başarı kodu kontrolü (Hazaclub genellikle 200 veya 0 döndürür)
    if data.get("code") not in (0, 200, None):
        logger.warning(f"Hazaclub API hata kodu {data.get('code')} – MID: {mid}")
        return None

    result = data.get("data")
    if not result:
        logger.info(f"Hazaclub'da kullanıcı bulunamadı – MID: {mid}")
    return result
