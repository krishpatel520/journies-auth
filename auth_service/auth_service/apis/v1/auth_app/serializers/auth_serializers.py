from rest_framework import serializers
import base64
import logging

logger = logging.getLogger(__name__)

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(required=True, write_only=True)
    
    def validate_password(self, value):
        """Handle hashed password from frontend"""
        # Password is already hashed on frontend
        # No decoding needed for SHA256 hash
        return value

class TokenVerifySerializer(serializers.Serializer):
    token = serializers.CharField(required=True)