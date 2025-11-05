from rest_framework import serializers
from auth_app.models.user_model import UserModel
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
        """Validate frontend-hashed password (SHA256)"""
        if not value or len(value) != 64:  # SHA256 produces 64-char hex string
            raise serializers.ValidationError("Invalid password hash format")
        return value
    
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
        
        # Apply server-side bcrypt hashing to frontend hash
        frontend_hash = validated_data.pop('password')
        user = UserModel.objects.create(**validated_data)
        user.set_password(frontend_hash)  # Apply bcrypt to frontend hash
        user.save()
        return user

class UserUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = UserModel
        fields = ['first_name', 'last_name', 'phone_number', 'password']
        extra_kwargs = {'password': {'write_only': True}}
    
    def validate_password(self, value):
        """Validate frontend-hashed password (SHA256)"""
        if not value or len(value) != 64:  # SHA256 produces 64-char hex string
            raise serializers.ValidationError("Invalid password hash format")
        return value
    
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
            instance.set_password(password)  # Apply bcrypt to frontend hash
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    
    def to_representation(self, instance):
        return UserSerializer(instance).data

class SignupSerializer(serializers.Serializer):
    tenant_name = serializers.CharField(max_length=100)
    tenant_code = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    phone_number = serializers.CharField(max_length=20, required=False)
    
    def validate_password(self, value):
        """Validate frontend-hashed password (SHA256)"""
        if not value or len(value) != 64:  # SHA256 produces 64-char hex string
            raise serializers.ValidationError("Invalid password hash format")
        return value
    
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
