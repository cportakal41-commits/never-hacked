from datetime import datetime, timedelta
from . import db
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import secrets


class User(db.Model):
    """Hazaclub'dan alınan kullanıcı verilerini saklar."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    mid = db.Column(db.Integer, unique=True, nullable=False)       # Hazaclub üye ID
    nick = db.Column(db.String(64), nullable=False)                 # Kullanıcı adı
    avatar = db.Column(db.String(512))                              # Avatar URL
    ip = db.Column(db.String(45))                                   # Son bağlantı IP (IPv6 dahil)
    device = db.Column(db.String(128))                              # Cihaz türü
    os = db.Column(db.String(64))                                   # İşletim sistemi sürümü
    login_time = db.Column(db.DateTime)                             # Son giriş zamanı
    created_at = db.Column(db.DateTime, default=datetime.utcnow)    # Kayıt oluşturma tarihi

    tokens = db.relationship("Token", backref="user", lazy=True)

    def __repr__(self):
        return f"<User {self.nick} (MID={self.mid})>"


class Token(db.Model):
    """
    Erişim token'larını ve JWT revokasyon durumunu saklar.
    Admin panelinden üretilen token'lar ile kullanıcılar sisteme giriş yapar.
    """

    __tablename__ = "tokens"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)   # Kullanıcının girdiği erişim anahtarı
    jti = db.Column(db.String(36), unique=True, nullable=True)                # JWT JTI (varsa)
    note = db.Column(db.String(128), default="Genel Erişim")                  # Token etiketi / notu
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True) # İlgili kullanıcı (varsa)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)             # Oluşturulma zamanı
    revoked = db.Column(db.Boolean, default=False)                            # İptal edildi mi?
    usage_count = db.Column(db.Integer, default=0)                            # Kaç kez sorgu yapıldı
    last_used_at = db.Column(db.DateTime, nullable=True)
    last_ip = db.Column(db.String(45), nullable=True)                          # Son kullanıcının bağlandığı IP                      # Son kullanım zamanı

    @staticmethod
    def generate_key():
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        part3 = secrets.token_hex(2).upper()
        return f"NH-{part1}-{part2}-{part3}"

    def __repr__(self):
        return f"<Token {self.key} (revoked={self.revoked})>"


class BlockedId(db.Model):
    """
    Sorgulanması yasaklanan/kısıtlanan Hazaclub MID'leri (Kara Liste).
    Admin panelinden eklenen bu ID'ler sorgulandığında kısıtlama hatası verir.
    """

    __tablename__ = "blocked_ids"

    id = db.Column(db.Integer, primary_key=True)
    mid = db.Column(db.Integer, unique=True, nullable=False, index=True)      # Kısıtlanan Hazaclub MID
    note = db.Column(db.String(255), default="Admin tarafından kısıtlı erişim") # Açıklama / Engel notu
    created_at = db.Column(db.DateTime, default=datetime.utcnow)            # Eklenme tarihi

    def __repr__(self):
        return f"<BlockedId MID={self.mid}>"


class TreasureScanLog(db.Model):
    """
    Token kullanıcılarının yaptığı hazine (İtem Al) tarama geçmişini saklar.
    """
    __tablename__ = "treasure_scan_logs"

    id = db.Column(db.Integer, primary_key=True)
    token_key = db.Column(db.String(64), nullable=False, index=True)
    token_note = db.Column(db.String(128), default="Genel Kullanıcı")
    found_summary = db.Column(db.String(255), default="Hedef ödül bulunamadı")
    raw_results = db.Column(db.Text, default="[]")  # JSON formatında bulunan kutular
    pages_scanned = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TreasureScanLog token={self.token_key} found={self.found_summary}>"


class RewardCooldown(db.Model):
    """
    Token bazlı ödül bekleme süreleri (cooldown).
    Örn: PRİNCE için 3 gün, HAZA HUNTER ve EFSANE ÇERÇEVE için 1 gün.
    """
    __tablename__ = "reward_cooldowns"

    id = db.Column(db.Integer, primary_key=True)
    token_key = db.Column(db.String(64), nullable=False, index=True)
    reward_id = db.Column(db.Integer, nullable=False)
    reward_name = db.Column(db.String(64), nullable=False)
    last_found_at = db.Column(db.DateTime, default=datetime.utcnow)
    cooldown_until = db.Column(db.DateTime, nullable=False)

    @property
    def is_active(self):
        return datetime.utcnow() < self.cooldown_until

    def __repr__(self):
        return f"<RewardCooldown {self.token_key} {self.reward_name} until {self.cooldown_until}>"


class TreasureClaimLog(db.Model):
    """
    Kullanıcıların ödül gönderme (light_up / claim) ve hazine işlemlerini saklar.
    Girilen Hazaclub tokeni, ID'si, IP adresi ve alınan ödüller burada kayıt altındadır.
    """
    __tablename__ = "treasure_claim_logs"

    id = db.Column(db.Integer, primary_key=True)
    token_key = db.Column(db.String(64), nullable=False, index=True)         # Sisteme giriş yapılan Never Hacked tokeni
    token_note = db.Column(db.String(128), default="Genel Kullanıcı")
    client_ip = db.Column(db.String(45), default="-")                       # Kullanıcının IP adresi
    action_type = db.Column(db.String(32), default="LIGHT_UP")               # LIGHT_UP veya SCAN
    hazaclub_mid = db.Column(db.Integer, nullable=True)                     # Girilen Hazaclub ID
    hazaclub_token = db.Column(db.String(255), nullable=True)               # Girilen Hazaclub Token (h_token)
    grid_id = db.Column(db.Integer, nullable=True)                          # Kutu ID
    page_no = db.Column(db.Integer, nullable=True)                          # Sayfa No
    item_name = db.Column(db.String(64), default="Bilinmeyen Ödül")          # PRINCE, HAZA HUNTER, EFSANE ÇERÇEVE
    reward_id = db.Column(db.Integer, nullable=True)                        # Reward ID
    status = db.Column(db.String(32), default="SUCCESS")                    # SUCCESS, FAILED
    response_summary = db.Column(db.String(512), default="")                # Hazaclub yanıtı / kazanılan ödül (EXP vb.)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)            # Tarih / Saat

    def __repr__(self):
        return f"<TreasureClaimLog {self.token_key} mid={self.hazaclub_mid} item={self.item_name}>"
