"""
Audit logging utilities for multi-service single-table pattern
Tracks field changes and enforces service ownership
"""
from auth_app.models import AuditLog
from django.conf import settings


class ServiceAuditLogger:
    """Audit logger for service-level field changes"""
    
    SERVICE_NAME = 'auth_service'
    
    # Auth Service owned fields
    AUTH_OWNED_FIELDS = {
        'email', 'password','is_active', 'veryfy_email', 'last_login',
        'is_email_verified', 'email_verification_token', 'email_verification_sent_at',
        'password_reset_token', 'password_reset_sent_at',
        'failed_login_attempts', 'locked_until', 'last_failed_login',
        'terms_accepted', 'is_deleted', 'deleted_at'
    }
    
    @classmethod
    def log_user_update(cls, user, changed_fields, old_values, new_values, request=None):
        """Log user field updates with ownership validation"""
        # Validate field ownership
        unauthorized_fields = set(changed_fields) - cls.AUTH_OWNED_FIELDS
        if unauthorized_fields:
            raise PermissionError(
                f"Service '{cls.SERVICE_NAME}' cannot update fields: {unauthorized_fields}"
            )
        
        payload = {
            'service': cls.SERVICE_NAME,
            'fields_changed': changed_fields,
            'old_values': cls._sanitize_values(old_values),
            'new_values': cls._sanitize_values(new_values),
        }
        
        AuditLog.log_action(
            action='user_update',
            user=user,
            tenant=user.tenant,
            resource='user',
            status='success',
            payload=payload,
            request=request
        )
    
    @classmethod
    def log_user_creation(cls, user, request=None):
        """Log user creation"""
        payload = {
            'service': cls.SERVICE_NAME,
            'action': 'user_created',
            'user_id': str(user.id),
            'email': user.email,
            'is_owner': user.is_owner,
        }
        
        AuditLog.log_action(
            action='user_create',
            user=user,
            tenant=user.tenant,
            resource='user',
            status='success',
            payload=payload,
            request=request
        )
    
    @classmethod
    def log_login_attempt(cls, email, success, request=None, reason=None):
        """Log login attempts"""
        payload = {
            'service': cls.SERVICE_NAME,
            'email': email,
            'success': success,
            'reason': reason,
        }
        
        AuditLog.log_action(
            action='login_attempt',
            resource='user',
            status='success' if success else 'failure',
            payload=payload,
            request=request
        )
    
    @classmethod
    def log_password_reset(cls, user, request=None):
        """Log password reset"""
        payload = {
            'service': cls.SERVICE_NAME,
            'action': 'password_reset',
            'user_id': str(user.id),
        }
        
        AuditLog.log_action(
            action='password_reset',
            user=user,
            tenant=user.tenant,
            resource='user',
            status='success',
            payload=payload,
            request=request
        )
    
    @classmethod
    def log_email_verification(cls, user, request=None):
        """Log email verification"""
        payload = {
            'service': cls.SERVICE_NAME,
            'action': 'email_verified',
            'user_id': str(user.id),
            'email': user.email,
        }
        
        AuditLog.log_action(
            action='email_verify',
            user=user,
            tenant=user.tenant,
            resource='user',
            status='success',
            payload=payload,
            request=request
        )
    
    @classmethod
    def log_account_lock(cls, user, reason, request=None):
        """Log account lock due to failed attempts"""
        payload = {
            'service': cls.SERVICE_NAME,
            'action': 'account_locked',
            'user_id': str(user.id),
            'reason': reason,
            'failed_attempts': user.failed_login_attempts,
        }
        
        AuditLog.log_action(
            action='account_lock',
            user=user,
            tenant=user.tenant,
            resource='user',
            status='success',
            payload=payload,
            request=request
        )
    
    @staticmethod
    def _sanitize_values(values):
        """Remove sensitive data from logged values"""
        if not values:
            return {}
        
        sanitized = values.copy()
        sensitive_fields = {'password', 'email_verification_token', 'password_reset_token'}
        
        for field in sensitive_fields:
            if field in sanitized:
                sanitized[field] = '***REDACTED***'
        
        return sanitized
