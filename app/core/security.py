import logging
import hashlib
import secrets
import base64
import hmac
from app.core.config import settings
from passlib.context import CryptContext

logger = logging.getLogger("app.security")
logger.setLevel(logging.INFO)

# Keep bcrypt context for fallback verification of legacy hashes
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _generate_salt_bytes() -> bytes:
    return secrets.token_bytes(settings.PASSWORD_SALT_BYTES)


def get_password_hash(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256.

    Stored format: pbkdf2_sha256$<iterations>$<salt_b64>$<dk_b64>
    """
    if not isinstance(password, str):
        password = str(password)
    salt = _generate_salt_bytes()
    dk = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt, settings.PASSWORD_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${settings.PASSWORD_HASH_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password. Supports PBKDF2-SHA256 and falls back to bcrypt for legacy hashes."""
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)
    # PBKDF2 format
    if isinstance(hashed_password, str) and hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _prefix, iterations_str, salt_b64, dk_b64 = hashed_password.split('$', 3)
            iterations = int(iterations_str)
            salt = base64.b64decode(salt_b64)
            dk = base64.b64decode(dk_b64)
            new_dk = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, iterations)
            return hmac.compare_digest(new_dk, dk)
        except Exception:
            logger.exception("Error verifying pbkdf2 password")
            return False

    # Fallback: bcrypt (for existing users hashed previously)
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        logger.exception("Error verifying password with fallback bcrypt")
        return False
