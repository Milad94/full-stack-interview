from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from .models import SyncRun
from .serializers import SyncRunSerializer
from .sync import enqueue_sync


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
