from rest_framework.viewsets import ModelViewSet

from apps.logs.services import write_operation_log
from apps.templates_cfg.views import SpecialistPermission
from .models import Processes, ProcessSteps
from .serializers import ProcessSerializer, ProcessStepSerializer


class ProcessViewSet(ModelViewSet):
    queryset = Processes.objects.all()
    serializer_class = ProcessSerializer
    permission_classes = [SpecialistPermission]

    def perform_create(self, serializer):
        process = serializer.save()
        write_operation_log(user=self.request.enterprise_user, operation_result=f"PROCESS_CREATED:{process.name}")


class ProcessStepViewSet(ModelViewSet):
    queryset = ProcessSteps.objects.select_related("process_id").all()
    serializer_class = ProcessStepSerializer
    permission_classes = [SpecialistPermission]

    def perform_create(self, serializer):
        step = serializer.save()
        write_operation_log(user=self.request.enterprise_user, operation_result=f"STEP_CREATED:{step.name}")
