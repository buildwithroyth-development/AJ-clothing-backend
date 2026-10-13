from django.http import JsonResponse
from django.urls import include, path

from products import firebase_client


def health_check(request):
    return JsonResponse({
        'status': 'ok',
        'message': 'AJ Clothing API is running',
        'firebase_configured': firebase_client.is_configured(),
    })


urlpatterns = [
    path('', health_check, name='health-check'),
    path('api/v1/', include('products.urls')),
]
