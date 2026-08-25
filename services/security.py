import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_ENV_PATH)


def _fernet() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Add a Fernet key to .env "
            "(python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("ENCRYPTION_KEY is not a valid Fernet key.") from exc


def encrypt_credential(plain_text: str) -> str:
    if not isinstance(plain_text, str) or not plain_text:
        raise ValueError("Credential to encrypt must be a non-empty string")
    return _fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_credential(cipher_text: str) -> str:
    if not isinstance(cipher_text, str) or not cipher_text:
        raise ValueError("Cipher text to decrypt must be a non-empty string")
    try:
        return _fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt credential with ENCRYPTION_KEY") from exc
