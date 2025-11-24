from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def decrypt_frontend_password(encrypted_password):
    """Decrypt AES-encrypted password from frontend."""
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
        logger.info(f"Encrypted data length: {len(encrypted_data)}, hex: {encrypted_data.hex()}")

        # Step 3: Extract IV and ciphertext (first 16 bytes = IV, rest = ciphertext)
        if len(encrypted_data) < 32:
            # Data is too short - likely just ciphertext, use fixed IV
            salt_hex = getattr(settings, 'SALT', None)
            if not salt_hex:
                raise ValueError("SALT not configured")
            iv = bytes.fromhex(salt_hex)
            ciphertext = encrypted_data
            logger.info(f"Using fixed IV, ciphertext length: {len(ciphertext)}")
        else:
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]
            logger.info(f"Extracted IV and ciphertext, ciphertext length: {len(ciphertext)}")

        # Step 4: Decrypt the ciphertext
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = cipher.decrypt(ciphertext)

        # Step 5: Unpad and decode
        try:
            unpadded = unpad(decrypted, AES.block_size)
        except ValueError:
            unpadded = decrypted

        decoded = unpadded.decode('utf-8')
        logger.info(f"Decryption successful: {decoded}")
        return decoded

    except Exception as e:
        logger.error(f"Password decryption failed: {e}", exc_info=True)
        return None
