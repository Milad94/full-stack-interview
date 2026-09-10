from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SyncRunViewSet

router = DefaultRouter()
router.register("sync-runs", SyncRunViewSet, basename="sync-run")

urlpatterns = [path("", include(router.urls))]
