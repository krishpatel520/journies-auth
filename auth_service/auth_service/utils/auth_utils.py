import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os
from decouple import config
import logging

logger = logging.getLogger(__name__)

def generate_rsa_keys():
    """Generate RSA key pair if not exists"""
    if not os.path.exists(settings.JWT_PRIVATE_KEY_PATH):
        logger.info("Generating new RSA key pair for JWT")
        try:
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            
            # Create keys directory if not exists
            os.makedirs(os.path.dirname(settings.JWT_PRIVATE_KEY_PATH), exist_ok=True)
            
            # Save private key
            with open(settings.JWT_PRIVATE_KEY_PATH, 'wb') as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Save public key
            public_key = private_key.public_key()
            with open(settings.JWT_PUBLIC_KEY_PATH, 'wb') as f:
                f.write(public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                ))
            
            logger.info("RSA key pair generated successfully")
        except Exception as e:
            logger.error(f"Failed to generate RSA keys: {e}")
            raise

def load_private_key():
    """Load private key from file"""
    try:
        generate_rsa_keys()  # Generate if not exists
        with open(settings.JWT_PRIVATE_KEY_PATH, 'rb') as f:
            logger.debug("Private key loaded successfully")
            return serialization.load_pem_private_key(f.read(), password=None)
    except Exception as e:
        logger.error(f"Failed to load private key: {e}")
        raise

def load_public_key():
    """Load public key from file"""
    try:
        generate_rsa_keys()  # Generate if not exists
        with open(settings.JWT_PUBLIC_KEY_PATH, 'rb') as f:
            logger.debug("Public key loaded successfully")
            return serialization.load_pem_public_key(f.read())
    except Exception as e:
        logger.error(f"Failed to load public key: {e}")
        raise

def generate_jwt(user_id, email, tenant_id, is_superuser=False, role_id=None, is_onboarding_complete=False, is_plan_purchased=False):
    """Generate JWT with tenant info and role"""
    try:
        with open(settings.JWT_PRIVATE_KEY_PATH, "r") as f:
            private_key = f.read()
        
        payload = {
            "sub": str(user_id),
            "email": email,
            "tid": str(tenant_id),
            "is_superuser": is_superuser,
            "is_onboarding_complete": is_onboarding_complete,
            "is_plan_purchased": is_plan_purchased,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iss": settings.JWT_ISSUER,
        }
        
        if role_id:
            payload["role_id"] = role_id
        
        token = jwt.encode(payload, private_key, algorithm=settings.JWT_ALGORITHM)
        logger.info(f"JWT generated for user {email} in tenant {tenant_id}")
        return token
    except Exception as e:
        logger.error(f"Failed to generate JWT for user {email}: {e}")
        raise

def validate_jwt(token, use_jwks=False, jwks_url=None):
    """Validate JWT token using local key or JWKS"""
    try:
        if not token:
            logger.debug("Empty token provided for validation")
            return None
        
        if use_jwks:
            from jwt import PyJWKClient
            if not jwks_url:
                jwks_url = f"http://127.0.0.1:{config('PORT')}/.well-known/jwks.json"
            
            logger.debug(f"Using JWKS validation with URL: {jwks_url}")
            jwks_client = PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            key = signing_key.key
        else:
            logger.debug("Using local key validation")
            key = load_public_key()
        
        payload = jwt.decode(
            token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER
        )
        
        # Additional validation
        if not payload.get('sub') or not payload.get('email'):
            logger.warning("JWT missing required claims (sub or email)")
            return None
        
        logger.debug(f"JWT validated successfully for user {payload.get('email')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT validation error: {e}")
        return None
