from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from auth_app.models.entity1_model import Entity1
from auth_service.apis.v1.auth_app.serializers.entity1_serializers import Entity1Serializer, Entity1CreateSerializer, Entity1UpdateSerializer

class Entity1ViewSet(viewsets.ModelViewSet):
    queryset = Entity1.objects.all()
    serializer_class = Entity1Serializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return Entity1CreateSerializer
        elif self.action in ['update', 'partial_update']:
            return Entity1UpdateSerializer
        return Entity1Serializer
