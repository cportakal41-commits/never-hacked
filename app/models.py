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
    last_used_at = db.Column(db.DateTime, nullable=True)                      # Son kullanım zamanı

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
