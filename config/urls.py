from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from shop.admin import site

urlpatterns = [path('admin/', site.urls), path('', include('shop.urls'))]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
