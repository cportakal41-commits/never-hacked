from datetime import datetime
from . import db
from werkzeug.security import generate_password_hash, check_password_hash


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

    # İlişki: bu kullanıcıya ait JWT token'ları
    tokens = db.relationship("Token", backref="user", lazy=True)

    def __repr__(self):
        return f"<User {self.nick} (MID={self.mid})>"


import uuid
import secrets

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
        """Rastgele güvenli formatta erişim anahtarı üretir. Örn: NH-A1B2-C3D4-E5F6"""
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        part3 = secrets.token_hex(2).upper()
        return f"NH-{part1}-{part2}-{part3}"

    def __repr__(self):
        return f"<Token {self.key} (revoked={self.revoked})>"
