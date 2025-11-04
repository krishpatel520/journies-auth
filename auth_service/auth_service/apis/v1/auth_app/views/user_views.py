from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
import logging

from auth_app.models.user_model import UserModel, RefreshToken
from auth_service.apis.v1.auth_app.serializers.user_serializers import UserSerializer, UserCreateSerializer, UserUpdateSerializer, SignupSerializer
from auth_service.apis.v1.auth_app.serializers.auth_serializers import (
    LoginSerializer, TokenVerifySerializer, EmailVerificationSerializer,
    ResendVerificationSerializer, ForgotPasswordSerializer, ResetPasswordSerializer,
    CheckVerificationStatusSerializer
)
from auth_service.utils.auth_utils import validate_jwt
from auth_service.utils.redis_client import redis_client
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

                            # Publish user creation event to Redis
                            redis_client.publish_event(settings.REDIS_CHANNEL, {
                                "tenant_id": str(tenant.id),
                                "user_id": str(user.id),
                                "email": user.email,
                                "first_name": user.first_name,
                                "last_name": user.last_name,
                                "full_name": user.full_name,
                                "is_superuser": user.is_superuser,
                                "is_active": user.is_active
                            })
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
                    # Check if user needs email verification
                    if not user.is_email_verified:
                        logger.warning(f"Login attempt for unverified user: {email}")
                        return Response({
                            'error': 'Please check your email to verify your account.',
                            'verification_required': True,
                            'email': user.email
                        }, status=status.HTTP_401_UNAUTHORIZED)
                    else:
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
                    is_active=False  # Inactive until email verified
                )
                
                user.set_password(data['password'])  # Apply bcrypt hashing
                user.save()
                
                # Send verification email
                try:
                    user.send_verification_email(request)
                    email_sent = True
                except Exception as e:
                    logger.error(f"Failed to send verification email: {e}")
                    email_sent = False

                # Publish user creation event to Redis
                redis_client.publish_event(settings.REDIS_CHANNEL, {
                    "tenant_id": str(tenant.id),
                    "user_id": str(user.id),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "full_name": full_name,
                    "is_superuser": user.is_superuser,
                    "is_active": user.is_active
                })

                logger.info(f"Successful signup for tenant: {tenant.code}, user: {user.email}")
                
                if email_sent:
                    return Response({
                        'message': "We have sent a verification link to your email.",
                        'email': user.email,
                        'verification_required': True
                    }, status=201)
                else:
                    return Response({
                        'message': 'Account created but failed to send verification email',
                        'email': user.email,
                        'verification_required': True,
                        'retry_available': True
                    }, status=201)
                
        except Exception as e:
            logger.error(f"Signup error: {e}")
            return Response({'error': 'Signup failed', 'details': str(e)}, status=500)
    
    @swagger_auto_schema(
        method='post',
        request_body=EmailVerificationSerializer,
        responses={200: 'Email verified successfully', 400: 'Invalid or expired token'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        """Verify email with token and redirect to select plan"""
        try:
            serializer = EmailVerificationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=400)
            
            token = serializer.validated_data['token']
            
            try:
                user = UserModel.objects.get(email_verification_token=token, is_email_verified=False)
                if user.verify_email(token):
                    user.is_active = True  # Activate user after email verification
                    user.save()
                    
                    logger.info(f"Email verified successfully for user: {user.email}")
                    
                    # Generate tokens for authenticated session
                    token_data = user.generate_jwt_token()
                    
                    return Response({
                        **token_data,
                        'message': 'Your email has been verified successfully! Your account is now active.',
                        'redirect_url': f"{getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')}/select-plan"
                    })
                else:
                    return Response({'error': 'Invalid or expired verification token'}, status=400)
                    
            except UserModel.DoesNotExist:
                return Response({'error': 'Invalid verification token'}, status=400)
                
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response({'error': 'Email verification failed'}, status=500)
    
    @swagger_auto_schema(
        method='post',
        request_body=ResendVerificationSerializer,
        responses={200: 'Verification email sent', 400: 'Invalid email or already verified'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def resend_verification(self, request):
        """Resend email verification"""
        try:
            serializer = ResendVerificationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=400)
            
            email = serializer.validated_data['email']
            
            try:
                user = UserModel.objects.get(email=email, is_email_verified=False)
                if user.is_active and user.is_email_verified:
                    return Response({'error': 'Email already verified'}, status=400)
                
                try:
                    user.send_verification_email(request)
                    logger.info(f"Verification email resent to: {email}")
                    return Response({'message': 'Verification link resent successfully.'})
                except Exception as e:
                    logger.error(f"Failed to resend verification email: {e}")
                    return Response({'error': 'Unable to resend link. Please check your connection and try again.'}, status=500)
                
            except UserModel.DoesNotExist:
                return Response({'error': 'User not found or email already verified'}, status=400)
                
        except Exception as e:
            logger.error(f"Resend verification error: {e}")
            return Response({'error': 'Unable to resend link. Please check your connection and try again.'}, status=500)
    
    @swagger_auto_schema(
        method='post',
        request_body=CheckVerificationStatusSerializer,
        responses={200: 'Verification status', 400: 'Invalid email'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def check_verification_status(self, request):
        """Check if user needs email verification"""
        try:
            serializer = CheckVerificationStatusSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=400)
            
            email = serializer.validated_data['email']
            
            try:
                user = UserModel.objects.get(email=email, is_deleted=False)
                
                if user.is_email_verified and user.is_active:
                    return Response({
                        'verified': True,
                        'message': 'Email already verified'
                    })
                else:
                    return Response({
                        'verified': False,
                        'message': 'Please check your email to verify your account.',
                        'resend_available': True
                    })
                    
            except UserModel.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Check verification status error: {e}")
            return Response({'error': "We're having trouble right now. Please refresh or try again later."}, status=500)
    
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
    
    @swagger_auto_schema(
        method='post',
        request_body=ForgotPasswordSerializer,
        responses={200: 'Reset link sent', 400: 'Invalid email', 404: 'Email not found'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """Send password reset link to email"""
        try:
            serializer = ForgotPasswordSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=400)
            
            email = serializer.validated_data['email']
            
            try:
                user = UserModel.objects.get(email=email, is_deleted=False)
                if not user.is_active:
                    return Response({'error': 'This email is not registered with Journies. Please try again or create a new account.'}, status=404)
                
                user.send_password_reset_email(request)
                logger.info(f"Password reset email sent to: {email}")
                return Response({'message': "We've sent a password reset link to your email. Please check your inbox or spam folder."})
                
            except UserModel.DoesNotExist:
                return Response({'error': 'This email is not registered with Journies. Please try again or create a new account.'}, status=404)
                
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            return Response({'error': 'Failed to send reset email'}, status=500)
    
    @swagger_auto_schema(
        method='post',
        request_body=ResetPasswordSerializer,
        responses={200: 'Password reset successful', 400: 'Invalid token or password', 404: 'Token expired'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """Reset password using token"""
        try:
            serializer = ResetPasswordSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=400)
            
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            
            try:
                user = UserModel.objects.get(password_reset_token=token, is_deleted=False)
                
                # Check if user is trying to reuse old password
                if user.check_password(new_password):
                    return Response({'error': 'This password was used recently. Please choose a new one.'}, status=400)
                
                if user.reset_password_with_token(token, new_password):
                    logger.info(f"Password reset successful for user: {user.email}")
                    return Response({'message': 'Your password has been reset successfully. Please sign in with your new password.'})
                else:
                    return Response({'error': 'Invalid or expired reset token'}, status=400)
                    
            except UserModel.DoesNotExist:
                return Response({'error': 'Invalid or expired reset token'}, status=400)
                
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            return Response({'error': 'Password reset failed'}, status=500)
    
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
    
    @swagger_auto_schema(
        method='post',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'current_password': openapi.Schema(type=openapi.TYPE_STRING),
                'new_password': openapi.Schema(type=openapi.TYPE_STRING)
            },
            required=['current_password', 'new_password']
        ),
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description='Bearer <token>',
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={200: 'Password changed successfully', 400: 'Validation error', 401: 'Invalid current password'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def change_password(self, request):
        """Change password for authenticated user"""
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if not auth_header.startswith('Bearer '):
                return Response({'error': 'Authorization header required'}, status=401)
            
            token = auth_header.split(' ')[1]
            payload = validate_jwt(token)
            
            if not payload:
                return Response({'error': 'Invalid token'}, status=401)
            
            current_password = request.data.get('current_password')
            new_password = request.data.get('new_password')
            
            if not current_password or not new_password:
                return Response({'error': 'Current and new passwords are required'}, status=400)
            
            try:
                user = UserModel.objects.get(id=payload['sub'])
                if user.is_deleted or not user.is_active:
                    return Response({'error': 'User account is inactive'}, status=401)
                
                # Verify current password using bcrypt
                if not user.check_password(current_password):
                    return Response({'error': 'Current password is incorrect'}, status=401)
                
                # Update to new password with bcrypt hashing
                user.set_password(new_password)
                user.save()
                
                # Revoke all refresh tokens to force re-login
                RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                
                logger.info(f"Password changed successfully for user: {user.email}")
                return Response({'message': 'Password changed successfully'})
                
            except UserModel.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return Response({'error': 'Password change failed'}, status=500)
