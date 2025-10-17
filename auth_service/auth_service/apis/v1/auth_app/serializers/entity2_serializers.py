from rest_framework import serializers
from auth_app.models.entity2_model import Entity2

class Entity2Serializer(serializers.ModelSerializer):
    class Meta:
        model = Entity2
        fields = '__all__'

class Entity2CreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity2
        fields = '__all__'

class Entity2UpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity2
        fields = '__all__'
