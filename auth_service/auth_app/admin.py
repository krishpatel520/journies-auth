from django.contrib import admin
from auth_app.models.user_model import UserModel
# from auth_app.models.entity2_model import Entity2
from auth_service.logger import logger_object

logger = logger_object('auth_app.admin')

@admin.register(UserModel)
class UserModelAdmin(admin.ModelAdmin):
    list_display = ['email', 'date_joined', 'is_active']
    list_filter = ['date_joined', 'is_active']
    search_fields = ['email']
    ordering = ['-date_joined']
    readonly_fields = ['date_joined', 'last_login']
    list_per_page = 25

