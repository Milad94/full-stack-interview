from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdjustmentViewSet, DashboardView, InvoiceViewSet, SyncRunViewSet

router = DefaultRouter()
router.register("adjustments", AdjustmentViewSet, basename="adjustment")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("sync-runs", SyncRunViewSet, basename="sync-run")

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("", include(router.urls)),
]
