from rest_framework import serializers
from auth_app.models.user_model import UserModel
import re
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    # profile_photo = serializers.SerializerMethodField()
    role_name = serializers.SerializerMethodField()
    property_name = serializers.SerializerMethodField()
    invited_by_name = serializers.SerializerMethodField()
    joining_date = serializers.SerializerMethodField()
    department_name = serializers.SerializerMethodField()
    
    class Meta:
        model = UserModel
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'phone_number', 'is_active', 
                  'created_at', 'role_name', 'property_name', 'invited_by_name', 
                  'status', 'joining_date', 'email_verification_sent_at', 'department_name']
        read_only_fields = ['id', 'created_at', 'role_name', 'property_name', 
                           'invited_by_name', 'joining_date', 'email_verification_sent_at', 'department_name']
    
    # def get_profile_photo(self, obj):
    #     """Return user profile photo or default"""
    #     if obj.profile_photo:
    #         return obj.profile_photo
    #     static_url = getattr(settings, 'STATIC_URL', '/static/')
    #     return f"{static_url}images/users.png"
    
    def get_role_name(self, obj):
        """Get role name from role_id"""
        if obj.role_id:
            try:
                from auth_app.models.role_model import Role
                role = Role.objects.get(id=obj.role_id)
                return role.name
            except:
                return f"role_{obj.role_id}"
        return None
    
    def get_property_name(self, obj):
        """Get property name from tenant"""
        if obj.tenant_id:
            try:
                from auth_app.models.property_model import Property
                property_obj = Property.objects.get(tenant_id=obj.tenant_id)
                return property_obj.property_name
            except:
                return None
        return None
    
    def get_invited_by_name(self, obj):
        """Get name of user who invited this user"""
        if obj.invited_by_id:
            try:
                invited_by_user = UserModel.objects.get(id=obj.invited_by_id)
                return invited_by_user.full_name or invited_by_user.email
            except UserModel.DoesNotExist:
                return None
        return None
    
    def get_joining_date(self, obj):
        """Return joining date - null for owner, signup date for invited users"""
        if obj.is_superuser or not obj.invited_by_id:
            return None
        return obj.date_joined
    
    def get_department_name(self, obj):
        """Get department name from department_id"""
        if obj.department_id:
            try:
                from auth_app.models.department_model import Department
                department = Department.objects.get(id=obj.department_id)
                return department.name
            except:
                return f"department_{obj.department_id}"
        return None

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=100, required=True)
    last_name = serializers.CharField(max_length=100, required=True)
    username = serializers.CharField(max_length=255, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role_id = serializers.IntegerField(required=False)
    terms_accepted = serializers.BooleanField()
    
    def validate_email(self, value):
        """Validate email format more strictly"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Enter a valid email address.")
        return value
    
    def validate_password(self, value):
        """Validate password is provided (decryption happens in view)"""
        if not value:
            raise serializers.ValidationError("Password is required")
        return value
    
    def validate_confirm_password(self, value):
        """Validate confirm password is provided (decryption happens in view)"""
        if not value:
            raise serializers.ValidationError("Confirm password is required")
        return value
    
    def validate(self, attrs):
        """Cross-field validation for password matching"""
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match'
            })
        
        return attrs
    
    def validate_phone_number(self, value):
        """Validate phone number format and uniqueness"""
        if value:
            # Remove spaces, dashes, and parentheses for validation
            cleaned = re.sub(r'[\s\-\(\)\+]', '', value)
            # Check if it contains only digits
            if not cleaned.isdigit():
                raise serializers.ValidationError("Please enter numbers only.")
            # Check if it's exactly 10 digits
            if len(cleaned) != 10:
                raise serializers.ValidationError("Phone number must be exactly 10 digits.")
            
            # Check uniqueness
            if UserModel.objects.filter(phone_number=value).exists():
                raise serializers.ValidationError("Phone number already exists")
        return value
    
    def validate_terms_accepted(self, value):
        """Validate that terms and conditions are accepted"""
        if not value:
            raise serializers.ValidationError("You must accept the terms and conditions to continue")
        return value
