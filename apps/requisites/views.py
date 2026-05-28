from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.documents.services import DocumentAutofillService
from apps.logs.services import write_operation_log
from apps.templates_cfg.views import SpecialistPermission
from apps.users.permissions import RoleBasedPermission
from .models import RequisiteLinks, Requisites, RequisiteValues
from .serializers import RequisiteLinkSerializer, RequisiteSerializer, RequisiteValueSerializer


class OperatorPermission(RoleBasedPermission):
    allowed_roles = {"ADMIN", "OPERATOR", "SPECIALIST"}


class RequisiteViewSet(ModelViewSet):
    queryset = Requisites.objects.select_related("document_type_id").all()
    serializer_class = RequisiteSerializer
    permission_classes = [SpecialistPermission]

    def perform_create(self, serializer):
        requisite = serializer.save()
        write_operation_log(user=self.request.enterprise_user, operation_result=f"REQUISITE_CREATED:{requisite.name}")


class RequisiteValueViewSet(ModelViewSet):
    queryset = RequisiteValues.objects.select_related("document_id", "requisite_id").all()
    serializer_class = RequisiteValueSerializer
    permission_classes = [OperatorPermission]


class RequisiteLinkViewSet(ModelViewSet):
    queryset = RequisiteLinks.objects.select_related("source_requisite_id", "target_requisite_id").all()
    serializer_class = RequisiteLinkSerializer
    permission_classes = [SpecialistPermission]

    def perform_create(self, serializer):
        link = serializer.save()
        write_operation_log(
            user=self.request.enterprise_user,
            operation_result=(
                f"REQUISITE_LINK_CREATED:{link.source_requisite_id.name}->{link.target_requisite_id.name}"
            ),
        )


class AutofillView(APIView):
    permission_classes = [OperatorPermission]

    def post(self, request):
        payload = DocumentAutofillService().build_document_form(
            document_type_id=request.data["document_type_id"],
            process_id=request.data["process_id"],
            object_id=request.data["object_id"],
            user=request.enterprise_user,
        )
        write_operation_log(user=request.enterprise_user, operation_result="AUTOFILL_REQUEST")
        return Response(payload, status=status.HTTP_200_OK)
