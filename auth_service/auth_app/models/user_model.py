from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta
import uuid
from auth_service.utils.auth_utils import generate_jwt
from auth_service.utils.email_templates import get_email_html_template

def validate_unique_email(value):
    """Validate email is unique for non-deleted users only"""
    if UserModel.objects.filter(email=value, is_deleted=False).exists():
        raise ValidationError('A user with this email already exists.')

# ============================================================================
# TENANT MODEL 
# ============================================================================

class Tenant(models.Model):
    """Tenants table"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    code = models.TextField(unique=True, null=True, blank=True)
    name = models.TextField(null=True, blank=True)
    status = models.TextField(default='active')
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
    """Auth-focused user model - shared table with Compass
    
    Multi-service single-table pattern:
    - Auth Service owns: email, password, is_active, auth tokens, brute force protection
    - Compass Service owns: first_name, last_name, full_name, phone_number, role_id
    - Shared: is_deleted, deleted_at, tenant_id
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    username = None
    email = models.EmailField(unique=True, validators=[validate_unique_email])
    
    # Auth Service Fields Only
    is_active = models.BooleanField(default=True, help_text="Account active/suspended status")
    created_at = models.DateTimeField(auto_now_add=True)
    date_joined = models.DateTimeField(default=timezone.now, verbose_name='date joined')
    last_login = models.DateTimeField(null=True, blank=True)
    
    # Compass Service Fields (read-only for Auth)
    first_name = models.CharField(max_length=100, null=False, blank=True)
    last_name = models.CharField(max_length=100, null=False, blank=True)
    full_name = models.TextField(null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    role_id = models.BigIntegerField(null=True, blank=True, help_text="Role ID from Compass service")
    invited_by_id = models.UUIDField(null=True, blank=True)
    department_id = models.BigIntegerField(null=True, blank=True)

    
    # Onboarding & Plan Status
    is_onboarding_complete = models.BooleanField(default=False, help_text="All onboarding steps completed")
    is_plan_purchased = models.BooleanField(default=False, help_text="User has active subscription plan")
    status = models.CharField(max_length=20, default='pending', help_text="User status: pending, active, suspended")

    
    # Soft delete (shared)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='deleted_users')
    updated_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_users')
    
    # Email Verification
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=255, null=True, blank=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Password Reset
    password_reset_token = models.CharField(max_length=255, null=True, blank=True)
    password_reset_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Brute Force Protection
    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    
    # Terms and Conditions
    terms_accepted = models.BooleanField(default=False)
    
    objects = UserModelManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'journies_usermodel'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        """Save user - field restrictions enforced at serializer/API level"""
        if self.pk is None and self.invited_by_id and not self.is_superuser:
            self.date_joined = timezone.now()
        super().save(*args, **kwargs)
    
    def generate_jwt_token(self):
        """Generate JWT token with role_id from database"""
        access_token = generate_jwt(
            user_id=str(self.id),
            email=self.email,
            tenant_id=str(self.tenant_id),
            is_superuser=self.is_superuser,
            role_id=self.role_id,
            is_onboarding_complete=self.is_onboarding_complete,
            is_plan_purchased=self.is_plan_purchased
        )
        
        refresh_token = RefreshToken.objects.create(user=self)
        
        return {
            'access_token': access_token,
            'refresh_token': str(refresh_token.token),
            'token_type': 'Bearer',
            'expires_in': 3600000
        }
    
    def soft_delete(self):
        """Soft delete user - append timestamp to email for reuse"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        # Append timestamp to email to free it up for reuse
        self.email = f"{self.email}#{int(self.deleted_at.timestamp())}"
        self.save(update_fields=['is_deleted', 'deleted_at', 'email'])
    
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
        
        self.save(update_fields=['failed_login_attempts', 'locked_until', 'last_failed_login'])
    
    def reset_failed_attempts(self):
        """Reset failed attempts on successful login"""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_failed_login = None
        self.save(update_fields=['failed_login_attempts', 'locked_until', 'last_failed_login'])
    
    def generate_verification_token(self):
        """Generate email verification token"""
        import secrets
        import logging
        logger = logging.getLogger(__name__)
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        self.save(update_fields=['email_verification_token', 'email_verification_sent_at'])
        logger.info(f"Generated verification token for {self.email}: {self.email_verification_token}")
        return self.email_verification_token
    
    def send_verification_email(self, request=None):
        """Send verification email with HTML template"""
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        
        token = self.generate_verification_token()
        base_url = getattr(settings, 'FRONTEND_URL', 'http://192.168.71.244/login')
        verification_url = f"{base_url}/verify-email?token={token}"
        logo_url = getattr(settings, 'LOGO_URL', None)
        
        if self.invited_by_id:
            # Invited user
            from auth_app.models.property_model import Property
            property = Property.objects.get(tenant_id=self.tenant_id)
            property_name = property.property_name
            
            subject = f"Join {property_name} Journey!"
            text_content = f"You've been invited to join {property_name}'s journey. Please verify your email to continue.\n\n{verification_url}"
            
            html_content = get_email_html_template(
                title=subject,
                content=text_content,
                button_text="Verify Email",
                button_url=verification_url,
                logo_url=logo_url
            )
        else:
            # Owner signup
            subject = "Verify your email address"
            content_html = f'<h1>Welcome to Journies!</h1><p>Please verify your email to continue.</p>'
            # text_content = """Welcome to Journies!
            # Please verify your email to continue.

            # """ 
            # + verification_url
                        
            html_content = get_email_html_template(
                title=subject,
                content=content_html,
                button_text="Verify Email",
                button_url=verification_url,
                logo_url=logo_url
            )
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=content_html,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'compass@journies.ai'),
            to=[self.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
    
    def verify_email(self, token):
        """Verify email with token - keep token until onboarding complete"""
        if self.email_verification_token == token:
            if not self.is_email_verified:
                self.is_email_verified = True
                self.status = 'pending'
                self.save(update_fields=['is_email_verified', 'status'])
            return True
        return False
    
    def activate_user(self):
        """Activate user and clear verification token"""
        self.status = 'active'
        self.email_verification_token = None
        self.save(update_fields=['status', 'email_verification_token'])
    
    def generate_password_reset_token(self):
        """Generate password reset token"""
        import secrets
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_sent_at = timezone.now()
        self.save(update_fields=['password_reset_token', 'password_reset_sent_at'])
        return self.password_reset_token
    
    def send_password_reset_email(self, request=None):
        """Send password reset email with HTML template"""
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        
        token = self.generate_password_reset_token()
        base_url = getattr(settings, 'FRONTEND_URL', 'http://192.168.71.244/login')
        reset_url = f"{base_url}/reset-password?token={token}"
        logo_url = getattr(settings, 'LOGO_URL', None)
        
        subject = 'Forgot password? Reset now'
        text_content = reset_url
        
        html_content = get_email_html_template(
            title="Forgot your password?",
            content="It happens to the best of us. To reset your password, click the button below.",
            button_text="Reset Password",
            button_url=reset_url,
            logo_url=logo_url
        )
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'compass@journies.ai'),
            to=[self.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
    
    def verify_password_reset_token(self, token):
        """Verify password reset token"""
        if self.password_reset_token == token:
            if self.password_reset_sent_at and (timezone.now() - self.password_reset_sent_at).total_seconds() < 3600:
                return True
        return False
    
    def reset_password_with_token(self, token, new_password):
        """Reset password using token"""
        if self.verify_password_reset_token(token):
            self.set_password(new_password)
            self.password_reset_token = None
            self.password_reset_sent_at = None
            self.save(update_fields=['password', 'password_reset_token', 'password_reset_sent_at'])
            
            # Revoke all refresh tokens
            RefreshToken.objects.filter(user=self, is_revoked=False).update(is_revoked=True)
            return True
        return False
    
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


class TokenBlacklist(models.Model):
    """Store blacklisted tokens for immediate revocation"""
    user_id = models.UUIDField(db_index=True)
    revoked_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=50, default='logout')
    
    class Meta:
        db_table = 'journies_token_blacklist'
        indexes = [
            models.Index(fields=['user_id', 'revoked_at']),
        ]
    
    @classmethod
    def revoke_user_tokens(cls, user_id, reason='logout'):
        """Add user to blacklist to revoke all tokens"""
        cls.objects.create(user_id=user_id, reason=reason)
    
    @classmethod
    def is_token_revoked(cls, user_id, token_issued_at):
        """Check if token is revoked based on blacklist"""
        return cls.objects.filter(
            user_id=user_id,
            revoked_at__gte=token_issued_at
        ).exists()


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
