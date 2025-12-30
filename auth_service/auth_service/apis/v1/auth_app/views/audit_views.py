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
    
    def _validate_auth(self, request):
        """Validate authorization and return user or error response"""
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None, Response({'success': False, 'errorMessage': 'Authorization header required'}, status=401)
        
        token = auth_header.split(' ')[1]
        payload = validate_jwt(token)
        if not payload:
            return None, Response({'success': False, 'errorMessage': 'Invalid token'}, status=401)
        
        try:
            user = UserModel.objects.get(id=payload['sub'])
            if user.is_deleted or not user.is_active:
                return None, Response({'success': False, 'errorMessage': 'User account is inactive'}, status=401)
            return user, None
        except UserModel.DoesNotExist:
            return None, Response({'success': False, 'errorMessage': 'User not found'}, status=404)
    
    def _get_query_params(self, request):
        """Extract and validate query parameters"""
        try:
            days = int(request.GET.get('days', 30))
        except (ValueError, TypeError):
            return None, Response({'success': False, 'errorMessage': 'Invalid days parameter'}, status=400)
        return {'days': days, 'action': request.GET.get('action'), 'status': request.GET.get('status')}, None
    
    def _format_logs(self, logs):
        """Format log records for response"""
        log_data = []
        try:
            for log in logs:
                log_data.append({
                    'id': str(log['id']),
                    'action': log['action'],
                    'resource': log['resource'],
                    'user_id': str(log['user_id']) if log['user_id'] else None,
                    'ip_address': log['ip_address'],
                    'status': log['status'],
                    'created_at': log['created_at'].isoformat(),
                    'payload': log['payload'] or {}
                })
        except (AttributeError, ValueError, KeyError) as e:
            logger.error(f"Error processing audit logs: {e}")
            return None, Response({'success': False, 'errorMessage': 'Error processing audit logs'}, status=500)
        return log_data, None
    
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
            user, error = self._validate_auth(request)
            if error:
                return error
            
            params, error = self._get_query_params(request)
            if error:
                return error
            
            since_date = timezone.now() - timedelta(days=params['days'])
            logs = AuditLog.objects.filter(
                tenant=user.tenant,
                created_at__gte=since_date
            )
            
            if params['action']:
                logs = logs.filter(action__icontains=params['action'])
            if params['status']:
                logs = logs.filter(status=params['status'])
            
            logs = logs.values('id', 'action', 'resource', 'user_id', 'ip_address', 'status', 'created_at', 'payload')[:1000]
            
            log_data, error = self._format_logs(logs)
            if error:
                return error
            
            return Response({
                'logs': log_data,
                'total': len(log_data),
                'filters': params
            })
                
        except Exception as e:
            logger.error(f"Audit logs error: {e}")
            return Response({'success': False, 'errorMessage': 'Failed to retrieve audit logs'}, status=500)