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
    
    @swagger_auto_schema(auto_schema=None)
    def list(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    @swagger_auto_schema(auto_schema=None)
    def create(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    @swagger_auto_schema(auto_schema=None)
    def update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    @swagger_auto_schema(auto_schema=None)
    def partial_update(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    @swagger_auto_schema(auto_schema=None)
    def destroy(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def retrieve(self, request, *args, **kwargs):
        """Get single user with proper error handling"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        except UserModel.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
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
            
            from auth_service.utils.password_utils import decrypt_frontend_password
            
            plain_password = decrypt_frontend_password(password)
            if not plain_password:
                logger.warning(f"Invalid password format for email: {email}")
                return Response({'error': 'Invalid email or password'}, status=status.HTTP_401_UNAUTHORIZED)
            
            try:
                user = UserModel.objects.get(email=email)
                
                if user.is_locked():
                    logger.warning(f"Login attempt for locked account: {email}")
                    return Response({'error': 'Account temporarily locked due to multiple failed attempts'}, status=status.HTTP_423_LOCKED)
                
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
                    return Response({'error': 'User account has been deleted'}, status=status.HTTP_401_UNAUTHORIZED)
                if not user.is_active:
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
                try:
                    failed_user = UserModel.objects.get(email=email)
                    if not failed_user.is_locked():
                        failed_user.increment_failed_attempts()
                except UserModel.DoesNotExist:
                    pass
            
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
                    'sub': payload['sub'],
                    'email': payload['email'],
                    'tid': payload['tid'],
                    'is_superuser': payload['is_superuser'],
                    'is_onboarding_complete': payload.get('is_onboarding_complete', False),
                    'is_plan_purchased': payload.get('is_plan_purchased', False),
                    'role_id': payload.get('role_id'),
                    'is_active': user.is_active,
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
            
            try:
                token_obj = RefreshToken.objects.get(token=refresh_token, is_revoked=False)
            except RefreshToken.DoesNotExist:
                return Response({'error': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
            
            if token_obj.is_expired():
                token_obj.revoke()
                return Response({'error': 'Refresh token expired'}, status=status.HTTP_401_UNAUTHORIZED)
            
            user = token_obj.user
            if not user.is_active or user.is_deleted:
                return Response({'error': 'User account is inactive'}, status=status.HTTP_401_UNAUTHORIZED)
            
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
            logger.info(f"Signup attempt for email: {data['email']}")
            
            if UserModel.objects.filter(email=data['email']).exists():
                logger.warning(f"Signup failed - email already exists: {data['email']}")
                return Response({
                    'error': 'Validation failed',
                    'details': {
                        'email': ['Email already exists']
                    }
                }, status=400)
            
            phone_number = data.get('phone_number')
            if phone_number:
                cleaned_phone = re.sub(r'[\s\-\(\)\+]', '', phone_number)
                if UserModel.objects.filter(phone_number=phone_number).exists():
                    logger.warning(f"Signup failed - phone number already exists: {phone_number}")
                    return Response({
                        'error': 'Validation failed',
                        'details': {
                            'phone_number': ['Phone number already exists']
                        }
                    }, status=400)
            
            with transaction.atomic():
                tenant = Tenant.objects.create(
                    name=None,
                    code=None,
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
                    phone_number=phone_number,
                    is_superuser=True,
                    is_active=False,
                    terms_accepted=data['terms_accepted']
                )
                
                user.set_password(data['password'])
                user.save()

                try:
                    user.send_verification_email(request)
                    email_sent = True
                except Exception as e:
                    logger.error(f"Failed to send verification email: {e}")
                    email_sent = False

                logger.info(f"Successful signup for user: {user.email}, tenant_id: {tenant.id}")
                
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
        """Verify email with token - reusable until first verification"""
        try:
            serializer = EmailVerificationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({'error': 'Invalid input', 'details': serializer.errors}, status=400)
            
            token = serializer.validated_data['token']
            
            try:
                user = UserModel.objects.get(email_verification_token=token)
                
                if user.is_email_verified:
                    return Response({'error': 'Email already verified'}, status=400)
                
                if user.verify_email(token):
                    user.is_active = True
                    user.save(update_fields=['is_active'])

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
                    return Response({'error': 'Invalid or expired verification token'}, status=400)
                    
            except UserModel.DoesNotExist:
                return Response({'error': 'Invalid verification token'}, status=400)
                
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response({'error': 'Email verification failed'}, status=500)
    
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
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if not auth_header:
                logger.warning("Logout attempt without authorization header")
                return Response({'error': 'Authorization header required'}, status=401)
            
            if not auth_header.startswith('Bearer '):
                logger.warning("Logout attempt with invalid authorization header format")
                return Response({'error': 'Invalid authorization header format'}, status=401)
            
            token_parts = auth_header.split(' ')
            if len(token_parts) != 2:
                logger.warning("Logout attempt with malformed authorization header")
                return Response({'error': 'Invalid authorization header format'}, status=401)
            
            token = token_parts[1]
            payload = validate_jwt(token)
            
            if not payload:
                logger.warning("Logout attempt with invalid token")
                return Response({'error': 'Invalid or expired token'}, status=401)
            
            user_id = payload.get('sub')
            user_email = payload.get('email')
            
            if user_id:
                try:
                    from auth_app.models.user_model import TokenBlacklist
                    user = UserModel.objects.get(id=user_id)
                    
                    active_tokens = RefreshToken.objects.filter(user=user, is_revoked=False)
                    if not active_tokens.exists():
                        logger.warning(f"Logout attempt for already logged out user: {user_email}")
                        return Response({'error': 'User is already logged out'}, status=400)
                    
                    active_tokens.update(is_revoked=True)
                    
                    TokenBlacklist.revoke_user_tokens(user_id, reason='logout')
                    
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
            confirm_password = serializer.validated_data['confirm_password']
            
            try:
                user = UserModel.objects.get(password_reset_token=token, is_deleted=False)
                
                if user.check_password(new_password):
                    return Response({'error': 'This password was used recently. Please choose a new one.'}, status=400)
                
                if user.reset_password_with_token(token, new_password, confirm_password):
                    logger.info(f"Password reset successful for user: {user.email}")
                    return Response({'message': 'Your password has been reset successfully. Please sign in with your new password.'})
                else:
                    return Response({'error': 'Invalid or expired reset token'}, status=400)
                    
            except UserModel.DoesNotExist:
                return Response({'error': 'Invalid or expired reset token'}, status=400)
                
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            return Response({'error': 'Password reset failed'}, status=500)
    
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
                return Response({'error': 'user_id is required'}, status=400)
            
            try:
                from auth_app.models.user_model import TokenBlacklist
                user = UserModel.objects.get(id=user_id)
                
                RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                TokenBlacklist.revoke_user_tokens(user_id, reason=reason)
                
                logger.info(f"Tokens revoked for user: {user.email}, reason: {reason}")
                return Response({'message': 'All tokens revoked successfully'})
                
            except UserModel.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Token revocation error: {e}")
            return Response({'error': 'Token revocation failed'}, status=500)
    
    
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
                
                if not user.check_password(current_password):
                    return Response({'error': 'Current password is incorrect'}, status=401)
                
                user.set_password(new_password)
                user.save()
                
                RefreshToken.objects.filter(user=user, is_revoked=False).update(is_revoked=True)
                
                logger.info(f"Password changed successfully for user: {user.email}")
                return Response({'message': 'Password changed successfully'})
                
            except UserModel.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Password change error: {e}")
            return Response({'error': 'Password change failed'}, status=500)
