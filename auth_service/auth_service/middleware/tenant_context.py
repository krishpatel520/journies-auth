from django.db import connection
from auth_app.models.user_model import Tenant
import jwt
import logging

logger = logging.getLogger(__name__)

def TenantContextMiddleware(get_response):
    """
    Middleware to extract tenant from JWT and set PostgreSQL session context.
    This enforces Row Level Security (RLS) at the database level for multi-tenant isolation.
    """
    def middleware(request):
        """Extract tenant from JWT and set database context"""
        try:
            # Extract JWT token from Authorization header
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return get_response(request)
            
            token = auth_header.split(" ")[1]
            
            # Decode JWT (without signature verification for performance)
            # Signature is already verified by JWT middleware
            payload = jwt.decode(token, options={"verify_signature": False})
            
            # Extract tenant ID from 'tid' claim
            tenant_id = payload.get("tid")
            if not tenant_id:
                logger.warning("JWT token missing 'tid' claim")
                return get_response(request)
            
            # Validate tenant exists and is active
            try:
                tenant = Tenant.objects.get(id=tenant_id, status='active')
                request.tenant = tenant
                request.tenant_id = tenant_id
                
                # Set PostgreSQL session variable for RLS
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL app.current_tenant = %s", [tenant_id])
                
                logger.debug(f"Tenant context set: {tenant.code} ({tenant_id})")
                
            except Tenant.DoesNotExist:
                logger.error(f"Invalid tenant ID in JWT: {tenant_id}")
                request.tenant = None
                request.tenant_id = None
                
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {e}")
        except Exception as e:
            logger.error(f"Error in tenant middleware: {e}")
        
        response = get_response(request)
        
        # Clean up database session
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")
        except Exception as e:
            logger.debug(f"Error resetting tenant context: {e}")
        
        return response
    return middleware