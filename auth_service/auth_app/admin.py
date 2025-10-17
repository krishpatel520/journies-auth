from django.contrib import admin
from auth_app.models.entity1_model import Entity1
from auth_app.models.entity2_model import Entity2
from auth_service.logger import logger_object

logger = logger_object('auth_app.admin')

@admin.register(Entity1)
class Entity1Admin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 25

@admin.register(Entity2)
class Entity2Admin(admin.ModelAdmin):
    list_display = ['title', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 25

