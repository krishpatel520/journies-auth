from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from datetime import timedelta
import uuid
from auth_service.utils.auth_utils import generate_jwt

# ============================================================================
# TENANT MODEL 
# ============================================================================

class Tenant(models.Model):
    """Tenants table"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    code = models.TextField(unique=True)
    name = models.TextField()
    status = models.TextField(default='active')
    plan = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'journies_tenant'
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class UserModelManager(BaseUserManager):
    def get_queryset(self):
        """Exclude soft-deleted users by default"""
        return super().get_queryset().filter(is_deleted=False)
    
    def all_with_deleted(self):
        """Get all users including soft-deleted"""
        return super().get_queryset()
    
    def deleted_only(self):
        """Get only soft-deleted users"""
        return super().get_queryset().filter(is_deleted=True)
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        
        # Create default tenant if not provided
        if 'tenant' not in extra_fields:
            tenant, created = Tenant.objects.get_or_create(
                code='default',
                defaults={
                    'name': 'Default Tenant',
                    'status': 'active'
                }
            )
            extra_fields['tenant'] = tenant
        
        return self.create_user(email, password, **extra_fields)

class UserModel(AbstractUser):
    """Users table with tenant isolation"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    username = None
    email = models.EmailField(unique=True)
    full_name = models.TextField(null=True, blank=True)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='deleted_users')
    updated_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_users')
    
    # Brute Force Protection
    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    
    objects = UserModelManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'journies_usermodel'
        ordering = ['-created_at']
    
    def generate_jwt_token(self):
        """Generate JWT token"""
        access_token = generate_jwt(
            user_id=str(self.id),
            email=self.email,
            tenant_id=str(self.tenant_id),
            tenant_code=self.tenant.code,
            is_superuser=self.is_superuser
        )
        
        refresh_token = RefreshToken.objects.create(user=self)
        
        return {
            'access_token': access_token,
            'refresh_token': str(refresh_token.token),
            'token_type': 'Bearer',
            'expires_in': 3600
        }
    
    def soft_delete(self, deleted_by=None):
        """Soft delete user"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save()
    
    def is_locked(self):
        """Check if account is locked due to failed attempts"""
        if self.locked_until and timezone.now() < self.locked_until:
            return True
        return False
    
    def increment_failed_attempts(self):
        """Increment failed login attempts and lock if needed"""
        self.failed_login_attempts += 1
        self.last_failed_login = timezone.now()
        
        # Lock account after 5 failed attempts for 15 minutes
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timedelta(minutes=15)
        
        self.save()
    
    def reset_failed_attempts(self):
        """Reset failed attempts on successful login"""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_failed_login = None
        self.save()
    
    def log_activity(self, action, request=None, status='success', payload=None):
        """Log user activity"""
        AuditLog.log_action(
            action=action,
            user=self,
            tenant=self.tenant,
            resource='user',
            status=status,
            payload=payload,
            request=request
        )
    
    def __str__(self):
        return self.email

class RefreshToken(models.Model):
    """Refresh tokens for JWT token refresh"""
    user = models.ForeignKey(UserModel, on_delete=models.CASCADE, related_name='refresh_tokens')
    token = models.CharField(max_length=255, unique=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'journies_refreshtoken'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)  # 7 days expiry
        super().save(*args, **kwargs)
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def revoke(self):
        self.is_revoked = True
        self.save()

class AuditLog(models.Model):
    """Audit logs for security and compliance"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    user_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=255)
    resource = models.CharField(max_length=255, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=50, default='success')
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'journies_auditlog'
        ordering = ['-created_at']
    
    @classmethod
    def log_action(cls, action, user=None, tenant=None, resource=None, status='success', payload=None, request=None):
        """Create audit log entry"""
        ip_address = None
        user_agent = None
        
        if request:
            # Get IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            # Get user agent
            user_agent = request.META.get('HTTP_USER_AGENT')
        
        return cls.objects.create(
            action=action,
            user_id=user.id if user else None,
            tenant=tenant,
            resource=resource,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
            payload=payload or {}
        )

