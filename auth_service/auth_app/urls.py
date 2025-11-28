from django.urls import path, include
from rest_framework.routers import DefaultRouter
from auth_app.views import index, email_files_list, email_file_detail
from auth_service.apis.v1.auth_app.views.user_views import UserViewSet
from auth_service.logger import logger_object
from django.conf import settings

logger = logger_object('auth_app.urls')

router = DefaultRouter()
router.register(r'users', UserViewSet)

urlpatterns = [
    path('', index, name='index'),
    path('v1/', include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += [
        path('email-files/', email_files_list, name='email_files_list'),
        path('email-files/<path:filename>', email_file_detail, name='email_file_detail'),
    ]

logger.info("auth_app URL patterns loaded")
