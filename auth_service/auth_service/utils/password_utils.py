from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def decrypt_frontend_password(encrypted_password):
    """Decrypt AES-encrypted password from frontend using fixed IV (SALT)."""
    try:
        # Step 1: Get and parse the encryption key
        crypt_key = getattr(settings, 'PASSWORD_CRYPT_KEY', '')
        if not crypt_key:
            raise ValueError("PASSWORD_CRYPT_KEY not configured")

        try:
            key_bytes = bytes.fromhex(crypt_key)
        except ValueError:
            raise ValueError("PASSWORD_CRYPT_KEY must be a valid hex string")

        if len(key_bytes) not in (16, 32):
            raise ValueError("PASSWORD_CRYPT_KEY must decode to 16 or 32 bytes")

        # Step 2: Decode the base64 encrypted password
        encrypted_data = base64.b64decode(encrypted_password)

        # Step 3: Use fixed IV from SALT
        salt_hex = getattr(settings, 'SALT', None)
        if not salt_hex:
            raise ValueError("SALT must be configured for fixed IV mode")

        try:
            iv = bytes.fromhex(salt_hex)
        except Exception:
            raise ValueError("SALT must be a valid hex string")

        if len(iv) != 16:
            raise ValueError("SALT must decode to 16 bytes")

        ciphertext = encrypted_data

        # Step 4: Decrypt the ciphertext
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)

        decrypted = cipher.decrypt(ciphertext)

        # Step 5: Unpad and decode
        unpadded = unpad(decrypted, AES.block_size)

        decoded = unpadded.decode('utf-8')

        return decoded

    except Exception as e:
        logger.error(f"Password decryption failed: {e}")
        return None