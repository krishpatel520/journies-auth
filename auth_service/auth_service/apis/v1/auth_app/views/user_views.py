from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone
import logging

from auth_app.models.user_model import UserModel, RefreshToken
from auth_service.apis.v1.auth_app.serializers.user_serializers import UserSerializer, UserCreateSerializer, UserUpdateSerializer, SignupSerializer
from auth_service.apis.v1.auth_app.serializers.auth_serializers import LoginSerializer, TokenVerifySerializer
from auth_service.utils.auth_utils import validate_jwt
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from datetime import datetime

logger = logging.getLogger(__name__)

class UserViewSet(viewsets.ModelViewSet):
    queryset = UserModel.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # Disable DRF authentication
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'login', 'verify_token']:
            return [AllowAny()]
        return [AllowAny()]  # For now, will add JWT middleware later
    
    def retrieve(self, request, *args, **kwargs):
        """Get single user with proper error handling"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except UserModel.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def update(self, request, *args, **kwargs):
        """Update user with proper error handling"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=False)
            if serializer.is_valid():
                # Set updated_by if user is authenticated
                if hasattr(request, 'jwt_payload') and request.jwt_payload:
                    try:
                        updated_by = UserModel.objects.get(id=request.jwt_payload['sub'])
                        instance.updated_by = updated_by
                    except UserModel.DoesNotExist:
                        pass
                serializer.save()
                return Response(serializer.data)
            return Response({'error': 'Invalid input'}, status=status.HTTP_400_BAD_REQUEST)
        except UserModel.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update user with proper error handling"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            if serializer.is_valid():
                # Set updated_by if user is authenticated
                if hasattr(request, 'jwt_payload') and request.jwt_payload:
                    try:
                        updated_by = UserModel.objects.get(id=request.jwt_payload['sub'])
                        instance.updated_by = updated_by
                    except UserModel.DoesNotExist:
                        pass
                serializer.save()
                return Response(serializer.data)
            return Response({'error': 'Invalid input'}, status=status.HTTP_400_BAD_REQUEST)
        except UserModel.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete user with proper error handling"""
        try:
            instance = self.get_object()
            # Get the user who is deleting (from JWT token)
            deleted_by = None
            if hasattr(request, 'jwt_payload') and request.jwt_payload:
                try:
                    deleted_by = UserModel.objects.get(id=request.jwt_payload['sub'])
                except UserModel.DoesNotExist:
                    pass
            
            instance.soft_delete(deleted_by=deleted_by)
            return Response({'message': 'User deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except UserModel.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid():
                # Check if email already exists
                email = serializer.validated_data.get('email')
                if UserModel.objects.filter(email=email).exists():
                    return Response({
                        'error': 'User creation failed'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Get tenant from JWT token
                logger.debug(f"Request user type: {type(request.user)}, value: {request.user}")
                
                # Try jwt_user first, then user
                jwt_payload = None
                if hasattr(request, 'jwt_user') and isinstance(request.jwt_user, dict):
                    jwt_payload = request.jwt_user
                elif hasattr(request, 'user') and isinstance(request.user, dict):
                    jwt_payload = request.user
                
                if jwt_payload:
                    tenant_id = jwt_payload.get('tid')
                    logger.debug(f"Extracted tenant_id: {tenant_id}")
                    if tenant_id:
                        from auth_app.models.user_model import Tenant
                        try:
                            tenant = Tenant.objects.get(id=tenant_id)
                            user = serializer.save(tenant=tenant)
                            logger.info(f"User created successfully: {user.email} in tenant: {tenant.code}")
                        except Tenant.DoesNotExist:
                            logger.error(f"Tenant not found: {tenant_id}")
                            return Response({'error': 'Invalid tenant'}, status=400)
                    else:
                        logger.error("No tenant ID in JWT token")
                        return Response({'error': 'No tenant in token'}, status=400)
                else:
                    logger.error(f"Authentication failed - user type: {type(getattr(request, 'user', None))}")
                    return Response({'error': 'Authentication required'}, status=401)
                
                return Response({
                    'message': 'User created successfully',
                    'user_id': user.id,
                    'email': user.email
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"User creation error: {e}")
            return Response({
                'error': 'User creation failed',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        method='post',
        request_body=LoginSerializer,
        responses={200: 'Login successful', 400: 'Validation error', 401: 'Invalid credentials'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def login(self, request):
        try:
            logger.info(f"Login attempt for email: {request.data.get('email')}")
            serializer = LoginSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"Login validation failed: {serializer.errors}")
                return Response({
                    'error': 'Invalid email or password'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            # Custom authentication for frontend-hashed passwords
            try:
                user = UserModel.objects.get(email=email)
                
                # Check if account is locked
                if user.is_locked():
                    logger.warning(f"Login attempt for locked account: {email}")
                    return Response({'error': 'Account temporarily locked due to multiple failed attempts'}, status=status.HTTP_423_LOCKED)
                
                # Verify password using Django's secure verification
                if user.check_password(password):  # bcrypt verification
                    # Authentication successful - reset failed attempts
                    user.reset_failed_attempts()
                else:
                    # Wrong password - increment failed attempts
                    user.increment_failed_attempts()
                    user = None
            except UserModel.DoesNotExist:
                user = None  # User not found
            
            if user:
                if user.is_deleted:
                    logger.warning(f"Login attempt for deleted user: {email}")
                    return Response({'error': 'User account has been deleted'}, status=status.HTTP_401_UNAUTHORIZED)
                if not user.is_active:
                    logger.warning(f"Login attempt for inactive user: {email}")
                    return Response({'error': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
                
                token_data = user.generate_jwt_token()
                logger.info(f"Successful login for user: {email}")
                return Response({
                    **token_data,
                    'message': 'Login successful'
                })
            else:
                # Failed login - check if we need to increment attempts for existing user
                try:
                    failed_user = UserModel.objects.get(email=email)
                    if not failed_user.is_locked():  # Only increment if not already locked
                        failed_user.increment_failed_attempts()
                except UserModel.DoesNotExist:
                    pass  # User doesn't exist, no need to track attempts
            
            logger.warning(f"Failed login attempt for email: {email}")
            return Response({'error': 'Invalid email or password'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Login error for {request.data.get('email')}: {e}")
            return Response({'error': 'Login failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        method='post',
        request_body=openapi.Schema(type=openapi.TYPE_OBJECT, properties={}),
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description='Bearer <token>',
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={200: 'Token valid', 400: 'Missing token', 401: 'Invalid token'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_token(self, request):
        """Verify JWT token for other microservices"""
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if not auth_header:
                return Response({'error': 'Authorization header missing'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not auth_header.startswith('Bearer '):
                return Response({'error': 'Invalid authorization header format. Use: Bearer <token>'}, status=status.HTTP_400_BAD_REQUEST)
            
            token_parts = auth_header.split(' ')
            if len(token_parts) != 2:
                return Response({'error': 'Invalid token format'}, status=status.HTTP_400_BAD_REQUEST)
            
            token = token_parts[1]
            if not token:
                return Response({'error': 'Token is empty'}, status=status.HTTP_400_BAD_REQUEST)
            
            payload = validate_jwt(token)
            
            if payload:
                # Check if user still exists and is active
                try:
                    user = UserModel.objects.get(id=payload['sub'])
                    if user.is_deleted:
                        return Response({'error': 'User account has been deleted'}, status=status.HTTP_401_UNAUTHORIZED)
                    if not user.is_active:
                        return Response({'error': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
                except UserModel.DoesNotExist:
                    return Response({'error': 'User not found'}, status=status.HTTP_401_UNAUTHORIZED)
                
                return Response({
                    'valid': True,
                    'exp': payload['exp']
                })
            return Response({'error': 'Invalid or expired token'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({'error': 'Token verification failed', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        method='post',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'refresh_token': openapi.Schema(type=openapi.TYPE_STRING)},
            required=['refresh_token']
        ),
        responses={200: 'Token refreshed', 400: 'Invalid refresh token', 401: 'Refresh token expired'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_token(self, request):
        """Refresh JWT token using refresh token"""
        try:
            refresh_token = request.data.get('refresh_token')
            if not refresh_token:
                return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Find and validate refresh token
            try:
                token_obj = RefreshToken.objects.get(token=refresh_token, is_revoked=False)
            except RefreshToken.DoesNotExist:
                return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
            
            if token_obj.is_expired():
                token_obj.revoke()
                return Response({'error': 'Refresh token expired'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # Generate new tokens
            user = token_obj.user
            if not user.is_active or user.is_deleted:
                return Response({'error': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # Revoke old refresh token and create new one
            token_obj.revoke()
            new_token_data = user.generate_jwt_token()
            
            return Response({
                **new_token_data,
                'message': 'Token refreshed successfully'
            })
            
        except Exception as e:
            return Response({'error': 'Token refresh failed', 'details': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        method='post',
        request_body=SignupSerializer,
        responses={201: 'Signup successful', 400: 'Validation error'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def signup(self, request):
        """Create tenant and admin user"""
        try:
            from auth_app.models.user_model import Tenant
            from django.db import transaction
            
            serializer = SignupSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Validation failed', 'details': serializer.errors}, status=400)
            
            data = serializer.validated_data
            logger.info(f"Signup attempt for tenant: {data['tenant_code']}, email: {data['email']}")
            
            # Check uniqueness
            if Tenant.objects.filter(code=data['tenant_code']).exists():
                logger.warning(f"Signup failed - tenant code already exists: {data['tenant_code']}")
                return Response({'error': 'Tenant code already exists'}, status=400)
            
            if UserModel.objects.filter(email=data['email']).exists():
                logger.warning(f"Signup failed - email already exists: {data['email']}")
                return Response({'error': 'Email already exists'}, status=400)
            
            with transaction.atomic():
                tenant = Tenant.objects.create(
                    name=data['tenant_name'],
                    code=data['tenant_code'],
                    status='active'
                )
                
                
                first_name = data.get('first_name', '')
                last_name = data.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()
                
                user = UserModel.objects.create(
                    tenant=tenant,
                    email=data['email'],
                    first_name=first_name,
                    last_name=last_name,
                    full_name=full_name,
                    is_superuser=True,
                    is_active=True
                )
                
                user.set_password(data['password'])  # Apply bcrypt hashing
                user.save()
                
                token_data = user.generate_jwt_token()
                
                logger.info(f"Successful signup for tenant: {tenant.code}, user: {user.email}")
                return Response({
                    **token_data,
                    'message': 'Signup successful'
                }, status=201)
                
        except Exception as e:
            logger.error(f"Signup error: {e}")
            return Response({'error': 'Signup failed', 'details': str(e)}, status=500)
    
    @swagger_auto_schema(
        method='post',
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description='Bearer <token>',
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={200: 'Logout successful', 400: 'Missing token', 401: 'Invalid token'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def logout(self, request):
        """Logout user by revoking refresh tokens"""
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if not auth_header.startswith('Bearer '):
                logger.warning("Logout attempt without proper authorization header")
                return Response({'error': 'Authorization header required'}, status=400)
            
            token = auth_header.split(' ')[1]
            payload = validate_jwt(token)
            
            if not payload:
                logger.warning("Logout attempt with invalid token")
                return Response({'error': 'Invalid token'}, status=401)
            
            user_id = payload.get('sub')
            user_email = payload.get('email')
            
            if user_id:
                try:
                    user = UserModel.objects.get(id=user_id)
                    
                    # Check if user has any active refresh tokens
                    active_tokens = RefreshToken.objects.filter(user=user, is_revoked=False)
                    if not active_tokens.exists():
                        logger.warning(f"Logout attempt for already logged out user: {user_email}")
                        return Response({'error': 'User is already logged out'}, status=400)
                    
                    # Revoke all active refresh tokens
                    active_tokens.update(is_revoked=True)
                    logger.info(f"Successful logout for user: {user_email}")
                    return Response({'message': 'Logout successful'})
                except UserModel.DoesNotExist:
                    logger.error(f"Logout failed - user not found: {user_id}")
                    return Response({'error': 'User not found'}, status=404)
            
            logger.warning("Logout failed - invalid token format")
            return Response({'error': 'Invalid token format'}, status=400)
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({'error': 'Logout failed', 'details': str(e)}, status=500)
    
    # @swagger_auto_schema(
    #     method='post',
    #     request_body=openapi.Schema(
    #         type=openapi.TYPE_OBJECT,
    #         properties={
    #             'email': openapi.Schema(type=openapi.TYPE_STRING),
    #             'new_password': openapi.Schema(type=openapi.TYPE_STRING)
    #         },
    #         required=['email', 'new_password']
    #     ),
    #     responses={200: 'Password reset successful', 400: 'Validation error', 404: 'User not found'}
    # )
    # @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    # def reset_password(self, request):
    #     """Reset password with frontend-hashed password"""
    #     try:
    #         email = request.data.get('email')
    #         new_password = request.data.get('new_password')
            
    #         if not email or not new_password:
    #             return Response({'error': 'Email and new password are required'}, status=400)
            
    #         try:
    #             user = UserModel.objects.get(email=email)
    #             if user.is_deleted or not user.is_active:
    #                 return Response({'error': 'User not found'}, status=404)
                
    #             # Store frontend hash directly
    #             user.password = new_password
    #             user.save()
                
    #             # Revoke all refresh tokens
    #             RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                
    #             logger.info(f"Password reset successful for user: {email}")
    #             return Response({'message': 'Password reset successful'})
                
    #         except UserModel.DoesNotExist:
    #             return Response({'error': 'User not found'}, status=404)
                
    #     except Exception as e:
    #         logger.error(f"Password reset error: {e}")
    #         return Response({'error': 'Password reset failed'}, status=500)
    
    # @swagger_auto_schema(
    #     method='post',
    #     request_body=openapi.Schema(
    #         type=openapi.TYPE_OBJECT,
    #         properties={
    #             'current_password': openapi.Schema(type=openapi.TYPE_STRING),
    #             'new_password': openapi.Schema(type=openapi.TYPE_STRING)
    #         },
    #         required=['current_password', 'new_password']
    #     ),
    #     manual_parameters=[
    #         openapi.Parameter(
    #             'Authorization',
    #             openapi.IN_HEADER,
    #             description='Bearer <token>',
    #             type=openapi.TYPE_STRING,
    #             required=True
    #         )
    #     ],
    #     responses={200: 'Password changed successfully', 400: 'Validation error', 401: 'Invalid current password'}
    # )
    # @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    # def change_password(self, request):
    #     """Change password with frontend-hashed passwords"""
    #     try:
    #         auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    #         if not auth_header.startswith('Bearer '):
    #             return Response({'error': 'Authorization header required'}, status=401)
            
    #         token = auth_header.split(' ')[1]
    #         payload = validate_jwt(token)
            
    #         if not payload:
    #             return Response({'error': 'Invalid token'}, status=401)
            
    #         current_password = request.data.get('current_password')
    #         new_password = request.data.get('new_password')
            
    #         if not current_password or not new_password:
    #             return Response({'error': 'Current and new passwords are required'}, status=400)
            
    #         try:
    #             user = UserModel.objects.get(id=payload['sub'])
    #             if user.is_deleted or not user.is_active:
    #                 return Response({'error': 'User account is inactive'}, status=401)
                
    #             # Verify current password (frontend hash comparison)
    #             if user.password != current_password:
    #                 return Response({'error': 'Current password is incorrect'}, status=401)
                
    #             # Update to new password (frontend hash)
    #             user.password = new_password
    #             user.save()
                
    #             # Revoke all refresh tokens to force re-login
    #             RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                
    #             logger.info(f"Password changed successfully for user: {user.email}")
    #             return Response({'message': 'Password changed successfully'})
                
    #         except UserModel.DoesNotExist:
    #             return Response({'error': 'User not found'}, status=404)
                
    #     except Exception as e:
    #         logger.error(f"Password change error: {e}")
    #         return Response({'error': 'Password change failed'}, status=500)
