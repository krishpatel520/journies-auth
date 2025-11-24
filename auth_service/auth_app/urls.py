from django.urls import path, include
from rest_framework.routers import DefaultRouter
from auth_app.views import index
from auth_service.apis.v1.auth_app.views.user_views import UserViewSet
from auth_service.logger import logger_object

logger = logger_object('auth_app.urls')

router = DefaultRouter()
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', index, name='index'),
    path('v1/', include(router.urls)),
]

logger.info("auth_app URL patterns loaded")
