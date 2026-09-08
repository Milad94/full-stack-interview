from django.urls import include, path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# TODO(candidate): register your viewsets here.
# router.register("invoices", InvoiceViewSet, basename="invoice")
# router.register("adjustments", AdjustmentViewSet, basename="adjustment")

urlpatterns = [
    path("", include(router.urls)),
]
