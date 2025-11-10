from rest_framework import serializers
from auth_app.models.user_model import UserModel
from auth_service.utils.password_utils import decrypt_frontend_password
import re
import logging

logger = logging.getLogger(__name__)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserModel
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'phone_number', 'is_active', 'date_joined']
        read_only_fields = ['id', 'date_joined']

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserModel
        fields = ['email', 'password', 'first_name', 'last_name', 'phone_number']
        extra_kwargs = {'password': {'write_only': True}}
    
    def validate_password(self, value):
        """Validate AES-encrypted password from frontend"""
        if not value:
            raise serializers.ValidationError("Password is required")
        
        # Decrypt the password
        plain_password = decrypt_frontend_password(value)
        if not plain_password:
            raise serializers.ValidationError("Invalid password format")
        
        # Return decrypted password for bcrypt hashing
        return plain_password
    
    def validate_phone_number(self, value):
        """Validate phone number format - exactly 10 digits"""
        if value:
            # Remove spaces, dashes, and parentheses for validation
            cleaned = re.sub(r'[\s\-\(\)\+]', '', value)
            # Check if it contains only digits
            if not cleaned.isdigit():
                raise serializers.ValidationError("Please enter numbers only.")
            # Check if it's exactly 10 digits
            if len(cleaned) != 10:
                raise serializers.ValidationError("Phone number must be exactly 10 digits.")
        return value
    
    def create(self, validated_data):
        first_name = validated_data.get('first_name', '')
        last_name = validated_data.get('last_name', '')
        validated_data['full_name'] = f"{first_name} {last_name}".strip()
        
        # Apply server-side bcrypt hashing to decrypted password
        plain_password = validated_data.pop('password')
        user = UserModel.objects.create(**validated_data)
        user.set_password(plain_password)  # Apply bcrypt to plain password
        user.save()
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = UserModel
        fields = ['first_name', 'last_name', 'phone_number', 'password']
        extra_kwargs = {'password': {'write_only': True}}
    
    def validate_password(self, value):
        """Validate AES-encrypted password from frontend"""
        if not value:
            raise serializers.ValidationError("Password is required")
        
        # Decrypt the password
        plain_password = decrypt_frontend_password(value)
        if not plain_password:
            raise serializers.ValidationError("Invalid password format")
        
        # Return decrypted password for bcrypt hashing
        return plain_password
    
    def validate_phone_number(self, value):
        """Validate phone number format - exactly 10 digits"""
        if value:
            # Remove spaces, dashes, and parentheses for validation
            cleaned = re.sub(r'[\s\-\(\)\+]', '', value)
            # Check if it contains only digits
            if not cleaned.isdigit():
                raise serializers.ValidationError("Please enter numbers only.")
            # Check if it's exactly 10 digits
            if len(cleaned) != 10:
                raise serializers.ValidationError("Phone number must be exactly 10 digits.")
        return value
    
    def update(self, instance, validated_data):
        # Auto-update full_name if first_name or last_name changed
        if 'first_name' in validated_data or 'last_name' in validated_data:
            first_name = validated_data.get('first_name', instance.first_name)
            last_name = validated_data.get('last_name', instance.last_name)
            validated_data['full_name'] = f"{first_name} {last_name}".strip()
        
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)  # Apply bcrypt to decrypted password
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
    def to_representation(self, instance):
        return UserSerializer(instance).data

class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    terms_accepted = serializers.BooleanField()
    
    def validate_email(self, value):
        """Validate email format more strictly"""
        if not value or '@' not in value:
            raise serializers.ValidationError("Enter a valid email address.")
        return value
    
    def validate_password(self, value):
        """Validate AES-encrypted password from frontend with strength requirements"""
        if not value:
            raise serializers.ValidationError("Password is required")
        
        # Decrypt the password
        plain_password = decrypt_frontend_password(value)
        if not plain_password:
            raise serializers.ValidationError("Invalid password format")
        
        # Password strength validation
        if len(plain_password) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long")
        
        if not re.search(r'[a-z]', plain_password):
            raise serializers.ValidationError("Password must contain at least one lowercase letter")
        
        if not re.search(r'[A-Z]', plain_password):
            raise serializers.ValidationError("Password must contain at least one uppercase letter")
        
        if not re.search(r'\d', plain_password):
            raise serializers.ValidationError("Password must contain at least one number")
        
        if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', plain_password):
            raise serializers.ValidationError("Password must contain at least one special character")
        
        # Return decrypted password for bcrypt hashing
        return plain_password
    
    def validate_confirm_password(self, value):
        """Validate AES-encrypted confirm password from frontend"""
        if not value:
            raise serializers.ValidationError("Confirm password is required")
        
        # Decrypt the confirm password
        plain_confirm_password = decrypt_frontend_password(value)
        if not plain_confirm_password:
            raise serializers.ValidationError("Invalid confirm password format")
        
        return plain_confirm_password
    
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