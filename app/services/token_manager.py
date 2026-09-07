import logging
from flask_jwt_extended import create_access_token, decode_token

logger = logging.getLogger(__name__)


def create_token_for_key(token_record) -> str:
    """
    Veritabanındaki bir Token kaydı için JWT erişim token'ı oluşturur ve JTI'yi bağlar.
    """
    from .. import db
    access_token = create_access_token(identity=str(token_record.id))
    jwt_data = decode_token(access_token)
    token_record.jti = jwt_data["jti"]
    db.session.commit()
    logger.info(f"Token için JWT oluşturuldu – Key={token_record.key}, jti={jwt_data['jti'][:8]}...")
    return access_token


def create_token(user_id: int) -> str:
    """Kullanıcı veya token ID için JWT oluşturur."""
    from .. import db
    from ..models import Token

    access_token = create_access_token(identity=str(user_id))
    jwt_data = decode_token(access_token)
    jti = jwt_data["jti"]

    token_record = Token.query.filter_by(id=user_id).first()
    if token_record:
        token_record.jti = jti
        db.session.commit()
    else:
        new_record = Token(key=Token.generate_key(), jti=jti, user_id=user_id)
        db.session.add(new_record)
        db.session.commit()

    return access_token


def is_token_revoked(jwt_header: dict, jwt_payload: dict) -> bool:
    """
    JWT blocklist callback'i – Flask-JWT-Extended tarafından her istekte çağrılır.

    Args:
        jwt_header: Decode edilmiş JWT header bilgisi
        jwt_payload: Decode edilmiş JWT payload

    Returns:
        True → token geçersiz sayılır (reddedilir)
        False → token geçerli
    """
    from ..models import Token

    jti = jwt_payload["jti"]
    token = Token.query.filter_by(jti=jti).first()

    if token is None:
        # Veritabanında bulunmayan token'lar güvenlik gereği reddedilir
        logger.warning(f"Bilinmeyen token isteği – jti={jti[:8]}...")
        return True

    if token.revoked:
        logger.info(f"Revoke edilmiş token kullanım denemesi – jti={jti[:8]}...")

    return token.revoked
