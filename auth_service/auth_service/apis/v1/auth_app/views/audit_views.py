from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from datetime import timedelta
import logging

from auth_app.models.user_model import UserModel, AuditLog
from auth_service.utils.auth_utils import validate_jwt
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

logger = logging.getLogger(__name__)

class AuditViewSet(viewsets.ViewSet):
    """Audit log management endpoints"""
    permission_classes = [AllowAny]
    
    @swagger_auto_schema(
        method='get',
        manual_parameters=[
            openapi.Parameter(
                'Authorization',
                openapi.IN_HEADER,
                description='Bearer <token>',
                type=openapi.TYPE_STRING,
                required=True
            ),
            openapi.Parameter('days', openapi.IN_QUERY, description='Days to look back (default: 30)', type=openapi.TYPE_INTEGER),
            openapi.Parameter('action', openapi.IN_QUERY, description='Filter by action type', type=openapi.TYPE_STRING),
            openapi.Parameter('status', openapi.IN_QUERY, description='Filter by status (success/failed)', type=openapi.TYPE_STRING),
        ],
        responses={200: 'Audit logs retrieved', 401: 'Unauthorized'}
    )
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def logs(self, request):
        """Get audit logs for tenant"""
        try:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            if not auth_header.startswith('Bearer '):
                return Response({'error': 'Authorization header required'}, status=401)
            
            token = auth_header.split(' ')[1]
            payload = validate_jwt(token)
            
            if not payload:
                return Response({'error': 'Invalid token'}, status=401)
            
            try:
                user = UserModel.objects.get(id=payload['sub'])
                if user.is_deleted or not user.is_active:
                    return Response({'error': 'User account is inactive'}, status=401)
                
                # Get query parameters
                days = int(request.GET.get('days', 30))
                action_filter = request.GET.get('action')
                status_filter = request.GET.get('status')
                
                # Build query
                since_date = timezone.now() - timedelta(days=days)
                logs = AuditLog.objects.filter(
                    tenant=user.tenant,
                    created_at__gte=since_date
                )
                
                if action_filter:
                    logs = logs.filter(action__icontains=action_filter)
                
                if status_filter:
                    logs = logs.filter(status=status_filter)
                
                # Limit to 1000 records
                logs = logs[:1000]
                
                log_data = []
                for log in logs:
                    log_data.append({
                        'id': str(log.id),
                        'action': log.action,
                        'resource': log.resource,
                        'user_id': str(log.user_id) if log.user_id else None,
                        'ip_address': log.ip_address,
                        'status': log.status,
                        'created_at': log.created_at.isoformat(),
                        'payload': log.payload
                    })
                
                return Response({
                    'logs': log_data,
                    'total': len(log_data),
                    'filters': {
                        'days': days,
                        'action': action_filter,
                        'status': status_filter
                    }
                })
                
            except UserModel.DoesNotExist:
                return Response({'error': 'User not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Audit logs error: {e}")
            return Response({'error': 'Failed to retrieve audit logs'}, status=500)