from rest_framework import serializers
from auth_app.models.entity1_model import Entity1

class Entity1Serializer(serializers.ModelSerializer):
    class Meta:
        model = Entity1
        fields = '__all__'

class Entity1CreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity1
        fields = '__all__'

class Entity1UpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity1
        fields = '__all__'
