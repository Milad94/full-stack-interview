from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .dashboard import dashboard_summary
from .models import Adjustment, Invoice, SyncRun
from .pagination import AccountingTablePagination
from .serializers import AdjustmentSerializer, DashboardSerializer, InvoiceSerializer, SyncRunSerializer
from .sync import enqueue_sync


class InvoiceViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Invoice.objects.order_by("external_id")
    serializer_class = InvoiceSerializer
    pagination_class = AccountingTablePagination
    search_fields = ["external_id", "customer_name"]


class AdjustmentViewSet(viewsets.ModelViewSet):
    queryset = Adjustment.objects.select_related("invoice")
    serializer_class = AdjustmentSerializer
    pagination_class = AccountingTablePagination
    filterset_fields = ["currency"]
    search_fields = ["reason", "invoice__external_id", "invoice__customer_name"]


class DashboardView(APIView):
    def get(self, request):
        return Response(DashboardSerializer(dashboard_summary()).data)


class SyncRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = SyncRun.objects.all()
    serializer_class = SyncRunSerializer
    filterset_fields = ["status"]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request):
        run, queued = enqueue_sync()
        return Response(
            self.get_serializer(run).data,
            status=status.HTTP_202_ACCEPTED if queued else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
