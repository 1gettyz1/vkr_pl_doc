from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.users.permissions import RoleBasedPermission
from .models import OperationLog
from .serializers import OperationLogSerializer


class LogPermission(RoleBasedPermission):
    allowed_roles = {"ADMIN", "SPECIALIST"}


class OperationLogViewSet(ReadOnlyModelViewSet):
    queryset = OperationLog.objects.select_related("document_id", "step_id", "user_id").all()
    serializer_class = OperationLogSerializer
    permission_classes = [LogPermission]
