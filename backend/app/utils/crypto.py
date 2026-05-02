import base64
import hashlib

from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    from ..config import settings
    raw = hashlib.sha256(settings.api_key_encryption_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_api_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
