from django.db.models import Q
from django.shortcuts import redirect, render
from django.http import FileResponse, Http404
from django.views import View
import json
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.bpm.models import BusinessProcessInstance, FieldSourceRule, ProcessDocumentInstance
from apps.documents.models import Documents
from apps.documents.serializers import DocumentSerializer
from apps.documents.services import DocumentAutofillService, generate_document, move_document
from apps.logs.services import write_operation_log
from apps.logs.models import OperationLog
from apps.processes.models import ProcessSteps, Processes
from apps.requisites.models import RequisiteLinks, Requisites, RequisiteValues
from apps.requisites.services import validate_document_requisites
from apps.requisites.views import OperatorPermission
from apps.templates_cfg.models import DocumentTypes, ProductionObjects
from apps.users.permissions import get_request_user
from apps.users.ui_permissions import LoginRequiredRoleMixin


class DocumentViewSet(ModelViewSet):
    queryset = Documents.objects.select_related("document_type_id", "object_id", "user_id", "process_id").all()
    serializer_class = DocumentSerializer
    permission_classes = [OperatorPermission]

    @action(detail=True, methods=["post"])
    def save_values(self, request, pk=None):
        document = self.get_object()
        values_payload = request.data.get("values", [])
        for item in values_payload:
            RequisiteValues.objects.update_or_create(
                document_id=document,
                requisite_id_id=item["requisite_id"],
                defaults={"value": str(item.get("value", "")).strip()},
            )
        errors = validate_document_requisites(document)
        document.status = "filled" if not errors else "draft"
        document.save(update_fields=["status"])
        write_operation_log(user=request.enterprise_user, document=document, operation_result="DOCUMENT_SAVED")
        if errors:
            return Response({"status": document.status, "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": document.status})

    @action(detail=True, methods=["post"])
    def change_status(self, request, pk=None):
        document = self.get_object()
        new_status = request.data.get("status", "draft")
        document.status = new_status
        document.save(update_fields=["status"])
        write_operation_log(user=request.enterprise_user, document=document, operation_result=f"STATUS_CHANGED:{new_status}")
        return Response({"document_id": document.document_id, "status": document.status})

    @action(detail=True, methods=["post"])
    def route(self, request, pk=None):
        document = self.get_object()
        enterprise_user = getattr(request, "enterprise_user", None) or get_request_user(request)
        result = request.data.get("operation_result", "APPROVED")
        payload = move_document(document, enterprise_user or document.user_id, result)
        return Response(payload)


class DocumentGenerationView(APIView):
    permission_classes = [OperatorPermission]

    def post(self, request, document_id):
        document = Documents.objects.get(document_id=document_id)
        enterprise_user = getattr(request, "enterprise_user", None) or get_request_user(request)
        values_payload = request.data.get("values", [])
        try:
            generate_document(document, values_payload, enterprise_user or document.user_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"document_id": document.document_id, "status": document.status})


class UIDocumentListView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST", "OPERATOR"}
    def get(self, request):
        queryset = Documents.objects.select_related("document_type_id", "user_id", "object_id")
        status_filter = request.GET.get("status")
        query = request.GET.get("q", "").strip()
        process_id = request.GET.get("process_id")
        bpi_id = request.GET.get("bpi_id")
        bpt_id = request.GET.get("bpt_id")
        role_name = request.enterprise_user.role_id.role_name
        if role_name == "OPERATOR":
            queryset = queryset.filter(user_id=request.enterprise_user)
        selected_instance = None
        instance_rows = []
        operator_templates = []
        if role_name == "OPERATOR":
            instance_qs = (
                BusinessProcessInstance.objects.filter(user=request.enterprise_user)
                .select_related("business_process_template")
                .order_by("-created_at")
            )
            operator_templates = list(
                BusinessProcessInstance.objects.filter(user=request.enterprise_user)
                .select_related("business_process_template")
                .values(
                    "business_process_template_id",
                    "business_process_template__name",
                )
                .distinct()
                .order_by("business_process_template__name")
            )
            if query:
                instance_qs = instance_qs.filter(instance_name__icontains=query)
            if bpt_id:
                instance_qs = instance_qs.filter(business_process_template_id=bpt_id)
            instance_rows = list(instance_qs)
        else:
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            if process_id:
                queryset = queryset.filter(process_id_id=process_id)
        if bpi_id:
            instance_qs = BusinessProcessInstance.objects.select_related("business_process_template")
            if role_name == "OPERATOR":
                instance_qs = instance_qs.filter(user=request.enterprise_user)
            selected_instance = instance_qs.filter(bpi_id=bpi_id).first()
            if selected_instance:
                queryset = queryset.filter(
                    bpm_document_slot__business_process_instance=selected_instance
                )
            else:
                queryset = queryset.none()
        if query and role_name != "OPERATOR":
            queryset = queryset.filter(Q(document_type_id__name__icontains=query) | Q(generated_html__icontains=query))
        documents = list(
            queryset.select_related(
                "document_type_id",
                "user_id",
                "object_id",
                "bpm_document_slot__business_process_instance__business_process_template",
            )[:100]
        )
        if role_name == "OPERATOR" and not selected_instance:
            documents = []
        return render(
            request,
            "ui/document_list.html",
            {
                "documents": documents,
                "processes": Processes.objects.all(),
                "bpi_id": bpi_id or "",
                "instance_rows": instance_rows,
                "selected_instance": selected_instance,
                "bpt_id": bpt_id or "",
                "operator_templates": operator_templates,
            },
        )

    def post(self, request):
        action = request.POST.get("action")
        document = Documents.objects.get(document_id=request.POST["document_id"])
        if request.enterprise_user.role_id.role_name == "OPERATOR" and document.user_id_id != request.enterprise_user.user_id:
            return redirect("ui-documents")
        if action == "delete":
            write_operation_log(user=request.enterprise_user, document=document, operation_result="DOCUMENT_DELETED")
            document.delete()
        return redirect("ui-documents")


class UICreateDocumentView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "OPERATOR", "SPECIALIST"}
    def get(self, request):
        context = {
            "document_types": DocumentTypes.objects.all(),
            "objects": ProductionObjects.objects.all(),
            "processes": Processes.objects.all(),
            "fields": [],
            "autofill_warnings": [],
            "has_table": False,
            "table_columns_json": "[]",
            "table_rows_json": "[]",
        }
        return render(request, "ui/create_document.html", context)

    def post(self, request):
        current_user = get_request_user(request)
        action_name = request.POST.get("action_name", "build")
        document_type_id = request.POST["document_type_id"]
        object_id = request.POST.get("object_id") or ProductionObjects.objects.first().object_id
        process_id = request.POST["process_id"]
        payload = DocumentAutofillService().build_document_form(
            document_type_id=document_type_id,
            process_id=process_id,
            object_id=object_id,
            user=current_user,
        )
        if action_name == "build":
            doc_type = DocumentTypes.objects.filter(document_type_id=int(document_type_id)).first()
            table_cols = [f for f in payload["fields"] if f.get("table_column")]
            table_columns_json = json.dumps(
                [
                    {
                        "requisite_id": f["requisite_id"],
                        "name": f["name"],
                        "placeholder_key": f.get("placeholder_key") or "",
                        "is_required": f["is_required"],
                        "data_type": f["data_type"],
                    }
                    for f in table_cols
                ],
                ensure_ascii=False,
            )
            context = {
                "document_types": DocumentTypes.objects.all(),
                "objects": ProductionObjects.objects.all(),
                "processes": Processes.objects.all(),
                "selected": {
                    "document_type_id": int(document_type_id),
                    "object_id": int(object_id),
                    "process_id": int(process_id),
                },
                "fields": payload["fields"],
                "autofill_warnings": payload["warnings"],
                "doc_type": doc_type,
                "has_table": bool(doc_type and doc_type.has_table_template),
                "table_columns_json": table_columns_json,
            }
            return render(request, "ui/create_document.html", context)

        document = Documents.objects.create(
            document_type_id_id=document_type_id,
            object_id_id=object_id,
            user_id=current_user,
            process_id_id=process_id,
            status="draft",
        )
        dt = DocumentTypes.objects.get(document_type_id=document_type_id)
        if dt.has_table_template:
            raw_t = request.POST.get("table_rows_json", "").strip()
            document.table_rows_json = raw_t if raw_t else json.dumps([{}], ensure_ascii=False)
            document.save(update_fields=["table_rows_json"])
        write_operation_log(user=current_user, document=document, operation_result="DOCUMENT_CREATED")
        field_map = {field["requisite_id"]: field for field in payload["fields"]}
        for key, value in request.POST.items():
            if key.startswith("req_"):
                req_id = int(key.replace("req_", ""))
                meta = field_map.get(req_id, {})
                if meta.get("table_column"):
                    continue
                value = (value or "").strip()
                if meta.get("field_kind") == "constant" and not value:
                    value = meta.get("value", "")
                RequisiteValues.objects.update_or_create(
                    document_id=document,
                    requisite_id_id=req_id,
                    defaults={"value": value},
                )
                if value and meta.get("source", "manual") == "auto":
                    write_operation_log(user=current_user, document=document, operation_result=f"AUTOFILLED:req_{req_id}")
                else:
                    write_operation_log(user=current_user, document=document, operation_result=f"MANUAL_VALUE:req_{req_id}")

        errors = validate_document_requisites(document)
        if errors:
            document.status = "draft"
            document.save(update_fields=["status"])
            doc_type = DocumentTypes.objects.filter(document_type_id=int(document_type_id)).first()
            table_cols = [f for f in payload["fields"] if f.get("table_column")]
            table_columns_json = json.dumps(
                [
                    {
                        "requisite_id": f["requisite_id"],
                        "name": f["name"],
                        "placeholder_key": f.get("placeholder_key") or "",
                        "is_required": f["is_required"],
                        "data_type": f["data_type"],
                    }
                    for f in table_cols
                ],
                ensure_ascii=False,
            )
            return render(
                request,
                "ui/create_document.html",
                {
                    "document_types": DocumentTypes.objects.all(),
                    "objects": ProductionObjects.objects.all(),
                    "processes": Processes.objects.all(),
                    "fields": payload["fields"],
                    "autofill_warnings": errors,
                    "selected": {
                        "document_type_id": int(document_type_id),
                        "object_id": int(object_id),
                        "process_id": int(process_id),
                    },
                    "doc_type": doc_type,
                    "has_table": bool(doc_type and doc_type.has_table_template),
                    "table_columns_json": table_columns_json,
                    "table_rows_json": getattr(document, "table_rows_json", None) or "[]",
                },
            )
        else:
            document.status = "filled"
            generate_document(document, [], current_user)
        document.save(update_fields=["status"])
        write_operation_log(user=current_user, document=document, operation_result="DOCUMENT_SAVED")
        return redirect("ui-document-preview", document_id=document.document_id)


class UIRequisiteFormView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "OPERATOR"}
    def get(self, request, document_id):
        document = Documents.objects.select_related("document_type_id").get(document_id=document_id)
        requisites = Requisites.objects.filter(document_type_id=document.document_type_id)
        current_values = {
            rv.requisite_id_id: rv.value
            for rv in RequisiteValues.objects.filter(document_id=document)
        }
        dt = document.document_type_id
        table_reqs = list(requisites.filter(is_table_column=True).order_by("requisite_id"))
        table_columns_json = json.dumps(
            [
                {
                    "requisite_id": r.requisite_id,
                    "name": r.name,
                    "placeholder_key": r.placeholder_key or "",
                    "is_required": r.is_required,
                    "data_type": r.data_type,
                }
                for r in table_reqs
            ],
            ensure_ascii=False,
        )
        return render(
            request,
            "ui/requisite_form.html",
            {
                "document": document,
                "requisites": requisites,
                "current_values": current_values,
                "has_table": getattr(dt, "has_table_template", False),
                "table_columns_json": table_columns_json,
                "table_rows_json": document.table_rows_json or "[]",
            },
        )

    def post(self, request, document_id):
        document = Documents.objects.get(document_id=document_id)
        raw_t = request.POST.get("table_rows_json", "").strip()
        if getattr(document.document_type_id, "has_table_template", False) and raw_t:
            try:
                json.loads(raw_t)
                document.table_rows_json = raw_t
                document.save(update_fields=["table_rows_json"])
            except json.JSONDecodeError:
                pass
        for key, value in request.POST.items():
            if key.startswith("req_"):
                req_id = int(key.replace("req_", ""))
                if Requisites.objects.filter(
                    requisite_id=req_id,
                    document_type_id=document.document_type_id,
                    is_table_column=True,
                ).exists():
                    continue
                RequisiteValues.objects.update_or_create(
                    document_id=document,
                    requisite_id_id=req_id,
                    defaults={"value": value},
                )
        return redirect("ui-documents")


class UITemplatesView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}
    def get(self, request):
        types = DocumentTypes.objects.prefetch_related("requisites").all()
        return render(request, "ui/templates.html", {"types": types})


class UIProcessesView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}
    def get(self, request):
        edit_id = request.GET.get("edit_id")
        edit_process = Processes.objects.filter(process_id=edit_id).first() if edit_id else None
        processes = Processes.objects.prefetch_related("steps").all()
        return render(request, "ui/processes.html", {"processes": processes, "edit_process": edit_process})

    def post(self, request):
        action = request.POST.get("action", "create")
        if action == "delete":
            process = Processes.objects.get(process_id=request.POST["process_id"])
            write_operation_log(user=request.enterprise_user, operation_result=f"PROCESS_DELETED:{process.name}")
            process.delete()
            return redirect("ui-processes")
        if action == "update":
            process = Processes.objects.get(process_id=request.POST["process_id"])
            process.name = request.POST["name"]
            process.description = request.POST.get("description", "")
            process.save()
            write_operation_log(user=request.enterprise_user, operation_result=f"PROCESS_UPDATED:{process.name}")
            return redirect("ui-processes")
        process = Processes.objects.create(name=request.POST["name"], description=request.POST.get("description", ""))
        write_operation_log(user=request.enterprise_user, operation_result=f"PROCESS_CREATED:{process.name}")
        return redirect("ui-processes")


def _bpm_preview_kind(rule):
    if not rule:
        return None
    if rule.source_type == FieldSourceRule.SOURCE_MANUAL:
        return "variable"
    if rule.source_type in (FieldSourceRule.SOURCE_DICTIONARY, FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT):
        return "constant"
    return "variable"


class UIDocumentPreviewView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST", "OPERATOR"}
    def get(self, request, document_id):
        document = Documents.objects.select_related(
            "document_type_id", "object_id", "user_id", "process_id"
        ).get(document_id=document_id)
        requisites = RequisiteValues.objects.filter(document_id=document).select_related("requisite_id")
        slot = (
            ProcessDocumentInstance.objects.filter(document_id=document.document_id)
            .select_related("process_document_template")
            .first()
        )
        rules = {}
        if slot:
            rules = {
                r.requisite_id: r
                for r in FieldSourceRule.objects.filter(process_document_template=slot.process_document_template)
            }
        requisite_rows = []
        for rv in requisites:
            rk = rules.get(rv.requisite_id_id)
            bpm_k = _bpm_preview_kind(rk)
            effective_kind = bpm_k if bpm_k is not None else rv.requisite_id.field_kind
            if getattr(rv.requisite_id, "is_table_column", False):
                continue
            requisite_rows.append({"rv": rv, "effective_kind": effective_kind})
        try:
            table_preview_rows = (
                json.loads(document.table_rows_json or "[]")
                if getattr(document.document_type_id, "has_table_template", False)
                else None
            )
        except json.JSONDecodeError:
            table_preview_rows = []
        if table_preview_rows is not None and not isinstance(table_preview_rows, list):
            table_preview_rows = []
        write_operation_log(
            user=request.enterprise_user,
            document=document,
            operation_result=f'Открыт предпросмотр документа «{document.document_type_id.name}» (№ {document.document_id}).',
        )
        return render(
            request,
            "ui/document_preview.html",
            {
                "document": document,
                "requisites": requisites,
                "requisite_rows": requisite_rows,
                "bpm_document_preview": bool(slot),
                "table_preview_rows": table_preview_rows,
            },
        )


class UIDocumentDownloadView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST", "OPERATOR"}

    def get(self, request, document_id):
        document = Documents.objects.get(document_id=document_id)
        if not document.generated_file:
            generate_document(document, [], request.enterprise_user)
            document.refresh_from_db()
            if not document.generated_file:
                raise Http404("Файл не сформирован")
        write_operation_log(
            user=request.enterprise_user,
            document=document,
            operation_result=(
                f'Скачан файл DOCX документа «{document.document_type_id.name}» '
                f'(№ {document.document_id}).'
            ),
        )
        return FileResponse(document.generated_file.open("rb"), as_attachment=True, filename=document.generated_file.name.split("/")[-1])


class UILogsView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}
    def get(self, request):
        logs = OperationLog.objects.select_related("user_id", "user_id__role_id", "document_id", "step_id").all()[:300]
        return render(request, "ui/logs.html", {"logs": logs})


class UIRequisiteLinksView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}
    def get(self, request):
        edit_id = request.GET.get("edit_id")
        edit_link = RequisiteLinks.objects.filter(req_link_id=edit_id).first() if edit_id else None
        return render(
            request,
            "ui/requisite_links.html",
            {
                "document_types": DocumentTypes.objects.all(),
                "requisites": Requisites.objects.select_related("document_type_id").all(),
                "links": RequisiteLinks.objects.select_related("source_requisite_id", "target_requisite_id").all(),
                "edit_link": edit_link,
                "target_requisite_id_param": request.GET.get("target_requisite_id", ""),
            },
        )

    def post(self, request):
        current_user = get_request_user(request)
        action = request.POST.get("action", "create")
        if action == "delete":
            link = RequisiteLinks.objects.get(req_link_id=request.POST["req_link_id"])
            write_operation_log(
                user=current_user,
                operation_result=f"REQUISITE_LINK_DELETED:{link.source_requisite_id.name}->{link.target_requisite_id.name}",
            )
            link.delete()
            return redirect("ui-requisite-links")
        if action == "update":
            link = RequisiteLinks.objects.get(req_link_id=request.POST["req_link_id"])
            link.source_requisite_id_id = request.POST["source_requisite_id"]
            link.target_requisite_id_id = request.POST["target_requisite_id"]
            link.inheritance_rule = request.POST.get("inheritance_rule", "copy_from_same_process_and_object")
            link.save()
            write_operation_log(
                user=current_user,
                operation_result=f"REQUISITE_LINK_UPDATED:{link.source_requisite_id.name}->{link.target_requisite_id.name}",
            )
            return redirect("ui-requisite-links")
        link = RequisiteLinks.objects.create(
            source_requisite_id_id=request.POST["source_requisite_id"],
            target_requisite_id_id=request.POST["target_requisite_id"],
            inheritance_rule=request.POST.get("inheritance_rule", "copy_from_same_process_and_object"),
        )
        if current_user:
            write_operation_log(
                user=current_user,
                operation_result=f"REQUISITE_LINK_CREATED:{link.source_requisite_id.name}->{link.target_requisite_id.name}",
            )
        return redirect("ui-requisite-links")


class UIRequisitesView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}

    def get(self, request):
        requisites = Requisites.objects.select_related("document_type_id").all().order_by("document_type_id__name")
        return render(request, "ui/specialist/requisites.html", {"requisites": requisites})


class UIProcessStepsView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}

    def get(self, request):
        edit_id = request.GET.get("edit_id")
        edit_step = ProcessSteps.objects.filter(step_id=edit_id).first() if edit_id else None
        steps = ProcessSteps.objects.select_related("process_id").all().order_by("process_id__name", "step_order")
        return render(
            request,
            "ui/specialist/process_steps.html",
            {"steps": steps, "processes": Processes.objects.all(), "edit_step": edit_step},
        )

    def post(self, request):
        action = request.POST.get("action", "create")
        if action == "delete":
            step = ProcessSteps.objects.get(step_id=request.POST["step_id"])
            write_operation_log(user=request.enterprise_user, operation_result=f"STEP_DELETED:{step.name}")
            step.delete()
            return redirect("ui-process-steps")
        if action == "update":
            step = ProcessSteps.objects.get(step_id=request.POST["step_id"])
            step.name = request.POST["name"]
            step.step_order = int(request.POST["step_order"])
            step.process_id_id = request.POST["process_id"]
            step.save()
            write_operation_log(user=request.enterprise_user, operation_result=f"STEP_UPDATED:{step.name}")
            return redirect("ui-process-steps")
        step = ProcessSteps.objects.create(
            name=request.POST["name"],
            step_order=int(request.POST["step_order"]),
            process_id_id=request.POST["process_id"],
        )
        write_operation_log(user=request.enterprise_user, operation_result=f"STEP_CREATED:{step.name}")
        return redirect("ui-process-steps")


class UIDocumentImportView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}

    def get(self, request):
        return render(
            request,
            "ui/specialist/document_import.html",
            {
                "objects": ProductionObjects.objects.all(),
                "processes": Processes.objects.all(),
            },
        )

    def post(self, request):
        uploaded = request.FILES.get("filled_file")
        new_type_name = request.POST.get("new_document_type_name", "").strip()
        mapping_raw = request.POST.get("requisite_mapping", "").strip()
        if not uploaded:
            return render(
                request,
                "ui/specialist/document_import.html",
                {
                    "error": "Выберите файл",
                    "objects": ProductionObjects.objects.all(),
                    "processes": Processes.objects.all(),
                },
            )
        if not new_type_name:
            return render(
                request,
                "ui/specialist/document_import.html",
                {
                    "error": "Укажите название нового типа документа",
                    "objects": ProductionObjects.objects.all(),
                    "processes": Processes.objects.all(),
                },
            )
        if DocumentTypes.objects.filter(name__iexact=new_type_name).exists():
            return render(
                request,
                "ui/specialist/document_import.html",
                {
                    "error": "Тип документа с таким названием уже существует",
                    "objects": ProductionObjects.objects.all(),
                    "processes": Processes.objects.all(),
                },
            )
        document_type = DocumentTypes.objects.create(name=new_type_name, description="Загруженный заполненный документ")
        mapping = []
        for line in mapping_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                mapping.append((key.strip(), value.strip()))
        document = Documents.objects.create(
            document_type_id=document_type,
            object_id_id=request.POST.get("object_id") or ProductionObjects.objects.first().object_id,
            process_id_id=request.POST["process_id"],
            user_id=request.enterprise_user,
            status="filled",
        )
        document.generated_file.save(uploaded.name, uploaded, save=True)
        for key, value in mapping:
            req, _ = Requisites.objects.get_or_create(
                document_type_id=document_type,
                placeholder_key=key,
                defaults={
                    "name": key,  # user-friendly field label for future linking
                    "data_type": "text",
                    "is_required": False,
                    "field_kind": "variable",
                },
            )
            RequisiteValues.objects.update_or_create(
                document_id=document,
                requisite_id=req,
                defaults={"value": value},
            )
        write_operation_log(user=request.enterprise_user, document=document, operation_result="DOCUMENT_IMPORTED_FOR_LINKS")
        return redirect("ui-template-configure", document_type_id=document_type.document_type_id)
