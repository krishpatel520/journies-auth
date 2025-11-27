from django.urls import path, include
from rest_framework.routers import DefaultRouter
from auth_app.views import index
from auth_service.apis.v1.auth_app.views.user_views import UserViewSet
from auth_service.logger import logger_object
from django.conf import settings
from django.conf.urls.static import static

logger = logger_object('auth_app.urls')

router = DefaultRouter()
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', index, name='index'),
    path('v1/', include(router.urls)),
] + static('/email-files/', document_root=settings.EMAIL_FILES_DIR)#TODO remove from production, this is for internal QA purpose.

logger.info("auth_app URL patterns loaded")
