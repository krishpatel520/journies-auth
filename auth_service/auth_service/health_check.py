
from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError
from django.views.decorators.http import require_http_methods

@require_http_methods(["GET"])
def health_check(request):
    db_conn = connections['default']
    try:
        db_conn.cursor()
        db_status = "ok"
    except OperationalError:
        db_status = "unhealthy"

    data = {
        "message": "Service is running",
        "database": db_status,
    }
    return JsonResponse(data)
