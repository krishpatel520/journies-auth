from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def decrypt_frontend_password(encrypted_password):
    """Decrypt AES-encrypted password sent from CryptoJS frontend."""
    try:
        key_bytes = bytes.fromhex(settings.PASSWORD_CRYPT_KEY)
        iv = bytes.fromhex(settings.SALT)

        # Decode base64 ciphertext
        ciphertext = base64.b64decode(encrypted_password)

        # Validate ciphertext is multiple of 16 bytes
        if len(ciphertext) % 16 != 0:
            raise ValueError(f"Invalid ciphertext length: {len(ciphertext)}")

        # AES CBC decryption with PKCS7 unpadding
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)

        return decrypted.decode("utf-8")

    except Exception as e:
        logger.error(f"Password decryption failed: {e}")
        return None
