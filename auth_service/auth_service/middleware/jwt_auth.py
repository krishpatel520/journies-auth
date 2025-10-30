from django.http import JsonResponse
from auth_service.utils.auth_utils import validate_jwt
import logging

logger = logging.getLogger(__name__)

def JWTAuthenticationMiddleware(get_response):
    """JWT Authentication Middleware for protected endpoints"""
    def middleware(request):
        # Public paths that don't need authentication (without prefix)
        public_paths = [
            '/api/v1/users/login/',
            '/api/v1/users/signup/',
            '/api/v1/users/verify_token/',
            '/api/v1/users/refresh_token/',
            '/.well-known/jwks.json',
            '/health/',
            '/swagger/',
            '/redoc/',
            '/static/',
            '/admin/'
        ]
        
        # Paths that need JWT authentication but have custom handling
        protected_paths = [
            '/api/v1/users/'  # User CRUD operations need JWT
        ]
        
        # Skip auth for public paths
        for path in public_paths:
            if request.path_info.startswith(path):
                logger.debug(f"Skipping auth for public path: {request.path_info}")
                return get_response(request)
        
        # Check if this is a protected path that needs JWT
        needs_jwt = False
        for path in protected_paths:
            if request.path_info.startswith(path):
                needs_jwt = True
                break
        
        # If not a known protected path, require JWT for all other endpoints
        if not needs_jwt:
            needs_jwt = True
        
        if needs_jwt:
            # Require JWT for protected endpoints
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if not auth_header.startswith("Bearer "):
                logger.warning(f"Missing or invalid auth header for {request.path_info}")
                return JsonResponse({"detail": "Missing or invalid token"}, status=401)

            token = auth_header.split(" ")[1]
            payload = validate_jwt(token)

            if not payload:
                logger.warning(f"Invalid JWT token for {request.path_info}")
                return JsonResponse({"detail": "Invalid or expired token"}, status=401)

            # Check if user still exists and is active
            try:
                from auth_app.models.user_model import UserModel
                user = UserModel.objects.get(id=payload['sub'])
                if user.is_deleted:
                    logger.warning(f"Access attempt by deleted user: {payload.get('email')}")
                    return JsonResponse({"detail": "User account has been deleted"}, status=401)
                if not user.is_active:
                    logger.warning(f"Access attempt by inactive user: {payload.get('email')}")
                    return JsonResponse({"detail": "User account is inactive"}, status=401)
            except UserModel.DoesNotExist:
                logger.warning(f"Access attempt by non-existent user: {payload.get('sub')}")
                return JsonResponse({"detail": "User not found"}, status=401)

            logger.debug(f"JWT authenticated user {payload.get('email')} for {request.path_info}")
            request.jwt_user = payload  # attach decoded user info
            request.user = payload  # Also set user for compatibility
        
        return get_response(request)
    return middleware