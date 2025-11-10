"""Password encryption/decryption utilities"""
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
from django.conf import settings
import hashlib
import logging

logger = logging.getLogger(__name__)

def decrypt_frontend_password(encrypted_password):
    """Decrypt AES-encrypted password from frontend"""
    try:
        crypt_key = getattr(settings, 'PASSWORD_CRYPT_KEY', '')
        if not crypt_key:
            raise ValueError("PASSWORD_CRYPT_KEY not configured")
        
        # CryptoJS uses UTF-8 key directly, padded to 32 bytes
        key_bytes = crypt_key.encode('utf-8')
        key_bytes = key_bytes.ljust(32, b'\0')[:32]
        
        # Decode base64
        encrypted_data = base64.b64decode(encrypted_password)
        
        # CryptoJS default uses CBC mode with random IV
        # IV is first 16 bytes, ciphertext is the rest
        if len(encrypted_data) < 16:
            raise ValueError("Invalid encrypted data length")
            
        iv = encrypted_data[:16]
        ciphertext = encrypted_data[16:]
        
        # Decrypt
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        
        return decrypted.decode('utf-8')
        
    except Exception as e:
        logger.error(f"Password decryption failed: {e}")
        return None