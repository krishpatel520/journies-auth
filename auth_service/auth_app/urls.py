from django.urls import path
from auth_app.views import index
from auth_service.logger import logger_object

logger = logger_object('auth_app.urls')

urlpatterns = [
    path('', index, name='index'),
]

logger.info("auth_app URL patterns loaded")

