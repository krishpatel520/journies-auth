from rest_framework import serializers
import base64
import logging

logger = logging.getLogger(__name__)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate_password(self, value):
        """Validate frontend-hashed password (SHA256)"""
        if not value or len(value) != 64:
            raise serializers.ValidationError("Invalid password hash format")
        return value

class TokenVerifySerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)

class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, write_only=True)
    confirm_password = serializers.CharField(required=True, write_only=True)
    
    def validate_new_password(self, value):
        """Validate frontend-hashed password (SHA256)"""
        if not value or len(value) != 64:
            raise serializers.ValidationError("Invalid password hash format")
        return value
    
    def validate_confirm_password(self, value):
        """Validate confirm password hash format"""
        if not value or len(value) != 64:
            raise serializers.ValidationError("Invalid password hash format")
        return value
    
    def validate(self, attrs):
        """Ensure both password hashes match"""
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Password hashes do not match")
        return attrs

class CheckVerificationStatusSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)