from django.http import JsonResponse
from cryptography.hazmat.primitives import serialization
import base64
import logging
from auth_service.utils.auth_utils import load_public_key

logger = logging.getLogger(__name__)

def jwks_view(request):
    """JWKS endpoint for other microservices"""
    try:
        logger.debug("JWKS endpoint accessed")
        public_key = load_public_key()
        
        # Get RSA public key numbers
        numbers = public_key.public_numbers()
        
        # Convert to base64url encoding (without padding)
        def int_to_base64url(value):
            byte_length = (value.bit_length() + 7) // 8
            return base64.urlsafe_b64encode(
                value.to_bytes(byte_length, 'big')
            ).decode('utf-8').rstrip('=')
        
        e = int_to_base64url(numbers.e)
        n = int_to_base64url(numbers.n)
        
        jwk = {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": "auth-service-key",
            "n": n,
            "e": e,
        }
        
        logger.debug("JWKS response generated successfully")
        return JsonResponse({"keys": [jwk]})
    except Exception as e:
        logger.error(f"JWKS endpoint error: {e}")
        return JsonResponse({"error": "Failed to generate JWKS"}, status=500)