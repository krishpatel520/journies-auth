from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.conf import settings
import logging

from auth_app.models.user_model import UserModel, RefreshToken
from auth_service.apis.v1.auth_app.serializers.user_serializers import UserSerializer, SignupSerializer
from auth_service.apis.v1.auth_app.serializers.auth_serializers import (
    LoginSerializer, EmailVerificationSerializer, ForgotPasswordSerializer, ResetPasswordSerializer,
)
from auth_service.utils.auth_utils import validate_jwt
from auth_service.utils.redis_client import redis_client
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import re

logger = logging.getLogger(__name__)

class UserViewSet(viewsets.ModelViewSet):
    queryset = UserModel.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def _disabled_method(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    @swagger_auto_schema(auto_schema=None)
    def list(self, request, *args, **kwargs):
        return self._disabled_method(request, *args, **kwargs)
    
    @swagger_auto_schema(auto_schema=None)
    def create(self, request, *args, **kwargs):
        return self._disabled_method(request, *args, **kwargs)
    
    @swagger_auto_schema(auto_schema=None)
    def update(self, request, *args, **kwargs):
        return self._disabled_method(request, *args, **kwargs)
    
    @swagger_auto_schema(auto_schema=None)
    def partial_update(self, request, *args, **kwargs):
        return self._disabled_method(request, *args, **kwargs)
    
    @swagger_auto_schema(auto_schema=None)
    def destroy(self, request, *args, **kwargs):
        return self._disabled_method(request, *args, **kwargs)
    
    def retrieve(self, request, *args, **kwargs):
        """Get single user details"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except UserModel.DoesNotExist:
            return Response({'success': False, 'errorMessage': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
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
                    'success': False,
                    'errorMessage': 'Invalid email or password'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            from auth_service.utils.password_utils import decrypt_frontend_password
            
            plain_password = decrypt_frontend_password(password)
            if not plain_password:
                logger.warning(f"Invalid password format for email: {email}")
                return Response({'success': False, 'errorMessage': 'Invalid email or password'}, status=status.HTTP_401_UNAUTHORIZED)
            
            try:
                user = UserModel.objects.get(email=email)
                
                if user.is_locked():
                    logger.warning(f"Login attempt for locked account: {email}")
                    return Response({'success': False, 'errorMessage': 'Account temporarily locked due to multiple failed attempts'}, status=status.HTTP_423_LOCKED)
                
                if user.check_password(plain_password):
                    user.reset_failed_attempts()
                else:
                    user.increment_failed_attempts()
                    user = None
            except UserModel.DoesNotExist:
                user = None
            
            if user:
                if user.is_deleted:
                    logger.warning(f"Login attempt for deleted user: {email}")
                    return Response({'success': False, 'errorMessage': 'User account has been deleted'}, status=status.HTTP_401_UNAUTHORIZED)
                if not user.is_active:
                    if not user.is_email_verified:
                        logger.warning(f"Login attempt for unverified user: {email}")
                        return Response({
                            'success': False,
                            'errorMessage': 'Please check your email to verify your account.',
                            'verification_required': True,
                            'email': user.email
                        }, status=status.HTTP_401_UNAUTHORIZED)
                    else:
                        logger.warning(f"Login attempt for inactive user: {email}")
                        return Response({'success': False, 'errorMessage': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
                
                token_data = user.generate_jwt_token()
                logger.info(f"Successful login for user: {email}")
                return Response({
                    **token_data,
                    'message': 'Login successful'
                })
            else:
                try:
                    failed_user = UserModel.objects.get(email=email)
                    if not failed_user.is_locked():
                        failed_user.increment_failed_attempts()
                except UserModel.DoesNotExist:
                    pass
            
            logger.warning(f"Failed login attempt for email: {email}")
            return Response({'success': False, 'errorMessage': 'Invalid email or password'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            logger.error(f"Login error for {request.data.get('email')}: {e}")
            return Response({'success': False, 'errorMessage': 'Login failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
            auth_header = request.META.get('HTTP_AUTHORIZATION', '').strip()
            if not auth_header:
                return Response({'success': False, 'errorMessage': 'Authorization header missing'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not auth_header.startswith('Bearer '):
                return Response({'success': False, 'errorMessage': 'Invalid authorization header format. Use: Bearer <token>'}, status=status.HTTP_400_BAD_REQUEST)
            
            token = auth_header[7:].strip()
            if not token:
                return Response({'success': False, 'errorMessage': 'Token is empty'}, status=status.HTTP_400_BAD_REQUEST)
            
            payload = validate_jwt(token)
            
            if payload:
                try:
                    user = UserModel.objects.get(id=payload['sub'])
                    if user.is_deleted:
                        return Response({'success': False, 'errorMessage': 'User account has been deleted'}, status=status.HTTP_401_UNAUTHORIZED)
                    if not user.is_active:
                        return Response({'success': False, 'errorMessage': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
                except UserModel.DoesNotExist:
                    return Response({'success': False, 'errorMessage': 'User not found'}, status=status.HTTP_401_UNAUTHORIZED)

                return Response({
                    'success': True,
                    'valid': True,
                    'sub': payload['sub'],
                    'email': payload['email'],
                    'tid': payload['tid'],
                    'is_superuser': payload['is_superuser'],
                    'is_onboarding_complete': user.is_onboarding_complete,
                    'is_plan_purchased': user.is_plan_purchased,
                    'role_id': payload.get('role_id'),
                    'is_active': user.is_active,
                    'exp': payload['exp']
                })
            return Response({'success': False, 'errorMessage': 'Invalid or expired token'}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({'success': False, 'errorMessage': 'Token verification failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
                return Response({'success': False, 'errorMessage': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                token_obj = RefreshToken.objects.get(token=refresh_token, is_revoked=False)
            except RefreshToken.DoesNotExist:
                return Response({'success': False, 'errorMessage': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
            
            if token_obj.is_expired():
                token_obj.revoke()
                return Response({'success': False, 'errorMessage': 'Refresh token expired'}, status=status.HTTP_401_UNAUTHORIZED)
            
            user = token_obj.user
            if not user.is_active or user.is_deleted:
                return Response({'success': False, 'errorMessage': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
            
            token_obj.revoke()
            new_token_data = user.generate_jwt_token()
            
            return Response({
                **new_token_data,
                'message': 'Token refreshed successfully'
            })
            
        except Exception as e:
            return Response({'success': False, 'errorMessage': 'Token refresh failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @swagger_auto_schema(
        method='post',
        request_body=SignupSerializer,
        responses={201: 'Signup successful', 400: 'Validation error'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def signup(self, request):
        """Create tenant and admin user, or complete invited user signup"""
        try:
            from auth_app.models.user_model import Tenant
            from django.db import transaction
            from auth_service.utils.password_utils import decrypt_frontend_password
            
            serializer = SignupSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'success': False, 'errorMessage': 'Validation failed', 'details': serializer.errors}, status=400)
            
            data = serializer.validated_data
            logger.info(f"Signup attempt for email: {data['email']}")
            
            existing_user = UserModel.objects.filter(email=data['email']).first()
            if existing_user and not existing_user.invited_by_id:
                logger.warning(f"Signup failed - email already exists: {data['email']}")
                return Response({'success': False, 'errorMessage': 'Email already exists'}, status=400)
            
            phone_number = data.get('phone_number')
            if phone_number and not existing_user:
                if UserModel.objects.filter(phone_number=phone_number).exists():
                    logger.warning(f"Signup failed - phone number already exists: {phone_number}")
                    return Response({'success': False, 'errorMessage': 'Phone number already exists'}, status=400)
            
            plain_password = decrypt_frontend_password(data['password'])
            if not plain_password:
                logger.warning(f"Signup failed - invalid password format for email: {data['email']}")
                return Response({'success': False, 'errorMessage': 'Invalid password format'}, status=400)
            
            if len(plain_password) < 8:
                return Response({'success': False, 'errorMessage': 'Password must be at least 8 characters long'}, status=400)
            if not re.search(r'[a-z]', plain_password):
                return Response({'success': False, 'errorMessage': 'Password must contain at least one lowercase letter'}, status=400)
            if not re.search(r'[A-Z]', plain_password):
                return Response({'success': False, 'errorMessage': 'Password must contain at least one uppercase letter'}, status=400)
            if not re.search(r'\d', plain_password):
                return Response({'success': False, 'errorMessage': 'Password must contain at least one number'}, status=400)
            if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', plain_password):
                return Response({'success': False, 'errorMessage': 'Password must contain at least one special character'}, status=400)
            
            plain_confirm = decrypt_frontend_password(data['confirm_password'])
            if not plain_confirm or plain_password != plain_confirm:
                return Response({'success': False, 'errorMessage': 'Passwords do not match'}, status=400)
            
            with transaction.atomic():
                if existing_user:
                    user = existing_user
                    user.first_name = data.get('first_name', '')
                    user.last_name = data.get('last_name', '')
                    user.full_name = f"{user.first_name} {user.last_name}".strip()
                    user.phone_number = phone_number
                    user.set_password(plain_password)
                    user.joined_date = timezone.now()
                    user.is_onboarding_complete = True
                    user.terms_accepted = data['terms_accepted']
                    user.save()
                    logger.info(f"Invited user completed signup: {user.email}")
                else:
                    tenant = Tenant.objects.create(
                        name=None,
                        code=None,
                        status='active'
                    )
                    
                    first_name = data.get('first_name', '')
                    last_name = data.get('last_name', '')
                    full_name = f"{first_name} {last_name}".strip()
                    
                    from auth_service.constants import ROLE_OWNER
                    
                    user = UserModel(
                        tenant=tenant,
                        email=data['email'],
                        first_name=first_name,
                        last_name=last_name,
                        full_name=full_name,
                        phone_number=phone_number,
                        role_id=ROLE_OWNER,
                        is_superuser=True,
                        is_active=False,
                        is_plan_purchased=False,
                        terms_accepted=data['terms_accepted']
                    )
                    user.set_password(plain_password)
                    user.save()
                    logger.info(f"New owner signup: {user.email}, tenant_id: {tenant.id}")

                # Send verification email inside transaction
                try:
                    user.send_verification_email(request)
                    logger.info(f"Verification email sent successfully to: {user.email}")
                except Exception as e:
                    logger.error(f"Failed to send verification email: {e}")
                    raise Exception("Failed to send verification email")

            return Response({
                'message': "We have sent a verification link to your email.",
                'email': user.email,
                'verification_required': True
            }, status=201)
                
        except Exception as e:
            logger.error(f"Signup error: {e}")
            return Response({'success': False, 'errorMessage': 'Signup failed'}, status=500)

    @swagger_auto_schema(
        method='post',
        request_body=EmailVerificationSerializer,
        responses={200: 'Email verified successfully', 400: 'Invalid or expired token'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_email(self, request):
        """Verify email with token - reusable until first verification"""
        try:
            serializer = EmailVerificationSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning(f"Email verification serializer validation failed: {serializer.errors}")
                return Response({'success': False, 'errorMessage': 'Invalid input', 'details': serializer.errors}, status=400)
            
            token = serializer.validated_data['token']
            logger.info(f"Attempting to verify email with token: {token[:20]}...")
            
            try:
                user = UserModel.objects.get(email_verification_token=token)
                logger.info(f"Found user with token: {user.email}, is_email_verified: {user.is_email_verified}")
                
                # For invited users, allow re-verification until onboarding is complete
                if user.is_email_verified and user.is_onboarding_complete:
                    return Response({'success': False, 'errorMessage': 'Email already verified'}, status=400)
                
                if user.verify_email(token):
                    user.is_active = True
                    user.status = 'active'
                    # Only clear token after onboarding is complete
                    if user.is_onboarding_complete:
                        user.email_verification_token = None
                    user.save(update_fields=['is_active', 'status', 'email_verification_token'])
                    logger.info(f"Email verified successfully for user: {user.email}")

                    # Publish event to Redis after email verification
                    try:
                        redis_client.publish_event(
                            settings.REDIS_STREAM_USERS,
                            {
                                "tenant_id": str(user.tenant.id),
                                "user_id": str(user.id),
                                "email": user.email,
                                "first_name": user.first_name,
                                "last_name": user.last_name,
                                "full_name": user.full_name,
                                "is_superuser": user.is_superuser,
                                "is_active": user.is_active,
                                "role_id": getattr(user, 'role_id', None),
                                "is_onboarding_complete": getattr(user, 'is_onboarding_complete', False),
                                "is_plan_purchased": getattr(user, 'is_plan_purchased', False)
                            },
                            operation="create"
                        )
                        logger.info(f"Published user verification event to Redis for user: {user.email}")
                    except Exception as e:
                        logger.error(f"Failed to publish user verification event to Redis: {e}")

                    token_data = user.generate_jwt_token()

                    return Response({
                        **token_data,
                        'message': 'Your email has been verified successfully! Your account is now active.'
                    })
                else:
                    logger.warning(f"verify_email method returned False for user: {user.email}")
                    return Response({'success': False, 'errorMessage': 'Invalid or expired verification token'}, status=400)
                    
            except UserModel.DoesNotExist:
                logger.warning(f"No user found with verification token: {token[:20]}...")
                return Response({'success': False, 'errorMessage': 'Invalid verification token'}, status=400)
                
        except Exception as e:
            logger.error(f"Email verification error: {e}", exc_info=True)
            return Response({'success': False, 'errorMessage': 'Email verification failed'}, status=500)
    
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
        """Logout user by revoking refresh tokens and blacklisting access tokens"""
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '').strip()
            if not auth_header:
                logger.warning("Logout attempt without authorization header")
                return Response({'success': False, 'errorMessage': 'Authorization header required'}, status=401)
            
            if not auth_header.startswith('Bearer '):
                logger.warning("Logout attempt with invalid authorization header format")
                return Response({'success': False, 'errorMessage': 'Invalid authorization header format'}, status=401)
            
            token = auth_header[7:].strip()
            if not token:
                logger.warning("Logout attempt with empty token")
                return Response({'success': False, 'errorMessage': 'Token is empty'}, status=401)
            payload = validate_jwt(token)
            
            if not payload:
                logger.warning("Logout attempt with invalid token")
                return Response({'success': False, 'errorMessage': 'Invalid or expired token'}, status=401)
            
            user_id = payload.get('sub')
            user_email = payload.get('email')
            
            if user_id:
                try:
                    from auth_app.models.user_model import TokenBlacklist
                    user = UserModel.objects.get(id=user_id)
                    
                    active_tokens = RefreshToken.objects.filter(user=user, is_revoked=False)
                    if not active_tokens.exists():
                        logger.warning(f"Logout attempt for already logged out user: {user_email}")
                        return Response({
                            'success': False,
                            'errorMessage': 'User is already logged out'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    active_tokens.update(is_revoked=True)
                    TokenBlacklist.revoke_user_tokens(user_id, reason='logout') 
                    
                    logger.info(f"Successful logout for user: {user_email}")
                    return Response({'message': 'Logout successful'})   
                except UserModel.DoesNotExist:  
                    logger.error(f"Logout failed - user not found: {user_id}")
                    return Response({'success': False, 'errorMessage': 'User not found'}, status=404)
            
            logger.warning("Logout failed - invalid token format")
            return Response({'success': False, 'errorMessage': 'Invalid token format'}, status=400)
            
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response({'success': False, 'errorMessage': 'Logout failed'}, status=500)
    
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
                return Response({'success': False, 'errorMessage': 'Invalid input', 'details': serializer.errors}, status=400)
            
            email = serializer.validated_data['email']
            
            try:
                user = UserModel.objects.get(email=email, is_deleted=False)
                if not user.is_active:
                    return Response({'success': False, 'errorMessage': 'This email is not registered with Journies. Please try again or create a new account.'}, status=404)
                
                if user.password_reset_sent_at:
                    time_since_last_reset = timezone.now() - user.password_reset_sent_at
                    if time_since_last_reset.total_seconds() < 300:
                        remaining_time = 300 - int(time_since_last_reset.total_seconds())
                        minutes = remaining_time // 60
                        seconds = remaining_time % 60
                        if minutes > 0:
                            time_str = f"{minutes} minute{'s' if minutes != 1 else ''} and {seconds} second{'s' if seconds != 1 else ''}"
                        else:
                            time_str = f"{seconds} second{'s' if seconds != 1 else ''}"
                        return Response({
                            'message': f"Password reset link already sent. Please check your email or try again in {time_str}."
                        })
                
                user.send_password_reset_email(request)
                logger.info(f"Password reset email sent to: {email}")
                return Response({'message': "We've sent a password reset link to your email. Please check your inbox or spam folder."})
                
            except UserModel.DoesNotExist:
                return Response({'success': False, 'errorMessage': 'This email is not registered with Journies. Please try again or create a new account.'}, status=404)
                
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            return Response({'success': False, 'errorMessage': 'Failed to send reset email'}, status=500)
    
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
                return Response({'success': False, 'errorMessage': 'Invalid input', 'details': serializer.errors}, status=400)
            
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            confirm_password = serializer.validated_data['confirm_password']
            
            try:
                user = UserModel.objects.get(password_reset_token=token, is_deleted=False)
                
                if user.check_password(new_password):
                    return Response({'success': False, 'errorMessage': 'This password was used recently. Please choose a new one.'}, status=400)
                
                if user.reset_password_with_token(token, new_password):
                    logger.info(f"Password reset successful for user: {user.email}")
                    return Response({'message': 'Your password has been reset successfully. Please sign in with your new password.'})
                else:
                    return Response({'success': False, 'errorMessage': 'Invalid or expired reset token'}, status=400)
                    
            except UserModel.DoesNotExist:
                return Response({'success': False, 'errorMessage': 'Invalid or expired reset token'}, status=400)
                
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            return Response({'success': False, 'errorMessage': 'Password reset failed'}, status=500)
    
    @swagger_auto_schema(
        method='post',
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_STRING),
                'reason': openapi.Schema(type=openapi.TYPE_STRING)
            },
            required=['user_id']
        ),
        responses={200: 'Tokens revoked successfully', 400: 'Validation error', 404: 'User not found'}
    )
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def revoke_tokens(self, request):
        """Revoke all tokens for a user (for other services)"""
        try:
            user_id = request.data.get('user_id')
            reason = request.data.get('reason', 'admin_action')
            
            if not user_id:
                return Response({'success': False, 'errorMessage': 'user_id is required'}, status=400)
            
            try:
                from auth_app.models.user_model import TokenBlacklist
                user = UserModel.objects.get(id=user_id)
                
                RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                TokenBlacklist.revoke_user_tokens(user_id, reason=reason)
                
                logger.info(f"Tokens revoked for user: {user.email}, reason: {reason}")
                return Response({'message': 'All tokens revoked successfully'})
                
            except UserModel.DoesNotExist:
                return Response({'success': False, 'errorMessage': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Token revocation error: {e}")
            return Response({'success': False, 'errorMessage': 'Token revocation failed'}, status=500)
    
    
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
            auth_header = request.META.get('HTTP_AUTHORIZATION', '').strip()
            if not auth_header or not auth_header.startswith('Bearer '):
                return Response({'success': False, 'errorMessage': 'Authorization header required'}, status=401)
            
            token = auth_header[7:].strip()
            payload = validate_jwt(token)
            
            if not payload:
                return Response({'success': False, 'errorMessage': 'Invalid token'}, status=401)
            
            current_password = request.data.get('current_password')
            new_password = request.data.get('new_password')
            
            if not current_password or not new_password:
                return Response({'success': False, 'errorMessage': 'Current and new passwords are required'}, status=400)
            
            try:
                user = UserModel.objects.get(id=payload['sub'])
                if user.is_deleted or not user.is_active:
                    return Response({'success': False, 'errorMessage': 'User account is inactive'}, status=401)
                
                if not user.check_password(current_password):
                    return Response({'success': False, 'errorMessage': 'Current password is incorrect'}, status=401)
                
                user.set_password(new_password)
                user.save()
                
                RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                
                logger.info(f"Password changed successfully for user: {user.email}")
                return Response({'message': 'Password changed successfully'})
                
            except UserModel.DoesNotExist:
                return Response({'success': False, 'errorMessage': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return Response({'success': False, 'errorMessage': 'Password change failed'}, status=500)
