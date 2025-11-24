from rest_framework import serializers
from auth_service.utils.password_utils import decrypt_frontend_password
import base64
import logging

logger = logging.getLogger(__name__)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)

class TokenVerifySerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

# class ResendVerificationSerializer(serializers.Serializer):
#     email = serializers.EmailField(required=True)

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate_new_password(self, value):
        """Validate AES-encrypted password from frontend"""
        if not value:
            raise serializers.ValidationError("Password is required")
        
        # Decrypt the password
        plain_password = decrypt_frontend_password(value)
        if not plain_password:
            raise serializers.ValidationError("Invalid password format")
        
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
        """Ensure both decrypted passwords match"""
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match'
            })
        return attrs

# class CheckVerificationStatusSerializer(serializers.Serializer):
#     email = serializers.EmailField(required=True)
