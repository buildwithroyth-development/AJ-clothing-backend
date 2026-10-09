import os
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health_check(request):
    db_status = "unknown"
    error_msg = None
    has_db_url = bool(os.environ.get('DATABASE_URL'))
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_status = "connected"
    except Exception as e:
        db_status = "failed"
        error_msg = str(e)

    return JsonResponse({
        "status": "ok",
        "message": "AJ Clothing API is running",
        "has_database_url": has_db_url,
        "database_status": db_status,
        "database_error": error_msg,
    })

urlpatterns = [
    path('', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('products.urls')),
]
