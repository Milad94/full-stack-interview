from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DashboardView, SyncRunViewSet

router = DefaultRouter()
router.register("sync-runs", SyncRunViewSet, basename="sync-run")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("", include(router.urls)),
]
