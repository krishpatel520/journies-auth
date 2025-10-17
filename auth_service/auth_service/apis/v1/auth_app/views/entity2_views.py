from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from auth_app.models.entity2_model import Entity2
from auth_service.apis.v1.auth_app.serializers.entity2_serializers import Entity2Serializer, Entity2CreateSerializer, Entity2UpdateSerializer

class Entity2ViewSet(viewsets.ModelViewSet):
    queryset = Entity2.objects.all()
    serializer_class = Entity2Serializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return Entity2CreateSerializer
        elif self.action in ['update', 'partial_update']:
            return Entity2UpdateSerializer
        return Entity2Serializer
