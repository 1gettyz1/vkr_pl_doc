"""DOCX и реквизиты шага БП — центр шаблона документа."""

from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.logs.services import write_operation_log
from apps.requisites.models import Requisites
from apps.templates_cfg.views import extract_placeholders_from_docx, sync_doc_type_table_fields_after_docx_upload
from apps.users.ui_permissions import LoginRequiredRoleMixin

from .models import BusinessProcessTemplate, ProcessDocumentTemplate


class UIBPMStepDocumentView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN", "SPECIALIST"}

    def get(self, request, bpt_id, pdt_id):
        bpt = get_object_or_404(BusinessProcessTemplate, bpt_id=bpt_id)
        pdt = get_object_or_404(
            ProcessDocumentTemplate.objects.select_related("document_type"),
            pdt_id=pdt_id,
            business_process_template=bpt,
        )
        dt = pdt.document_type
        requisites = Requisites.objects.filter(document_type_id=dt).order_by("requisite_id")
        extracted = []
        if dt.template_file and dt.template_file.name.lower().endswith(".docx"):
            try:
                extracted = extract_placeholders_from_docx(dt.template_file.path)
            except Exception:
                extracted = []
        return render(
            request,
            "ui/bpm/specialist/step_document.html",
            {
                "bpt": bpt,
                "pdt": pdt,
                "doc_type": dt,
                "requisites": requisites,
                "extracted_placeholders": extracted,
            },
        )

    def post(self, request, bpt_id, pdt_id):
        bpt = get_object_or_404(BusinessProcessTemplate, bpt_id=bpt_id)
        pdt = get_object_or_404(ProcessDocumentTemplate, pdt_id=pdt_id, business_process_template=bpt)
        dt = pdt.document_type
        action = request.POST.get("action", "")

        if action == "upload_docx":
            f = request.FILES.get("template_file")
            if not f:
                return redirect("ui-bpm-step-document", bpt_id=bpt.bpt_id, pdt_id=pdt.pdt_id)
            has_table = request.POST.get("has_table_template") == "on"
            dt.template_file.save(f.name, f, save=True)
            err = sync_doc_type_table_fields_after_docx_upload(dt, has_table)
            if err:
                write_operation_log(
                    user=request.enterprise_user,
                    operation_result=f"Ошибка DOCX шага «{pdt.name}»: {err}",
                )
                return redirect("ui-bpm-step-document", bpt_id=bpt.bpt_id, pdt_id=pdt.pdt_id)
            write_operation_log(
                user=request.enterprise_user,
                operation_result=(
                    f'Для шага «{pdt.name}» загружен DOCX; полей: {len(extract_placeholders_from_docx(dt.template_file.path))}.'
                ),
            )
            return redirect("ui-bpm-step-document", bpt_id=bpt.bpt_id, pdt_id=pdt.pdt_id)

        if action == "save_requisites":
            for req in Requisites.objects.filter(document_type_id=dt):
                req.name = request.POST.get(f"name_{req.requisite_id}", req.name).strip() or req.name
                req.data_type = request.POST.get(f"data_type_{req.requisite_id}", req.data_type)
                req.field_kind = request.POST.get(f"field_kind_{req.requisite_id}", req.field_kind)
                req.is_required = request.POST.get(f"is_required_{req.requisite_id}") == "on"
                req.save()
            write_operation_log(
                user=request.enterprise_user,
                operation_result=f'Обновлены реквизиты типа «{dt.name}» (шаг «{pdt.name}»).',
            )
            return redirect("ui-bpm-step-document", bpt_id=bpt.bpt_id, pdt_id=pdt.pdt_id)

        return redirect("ui-bpm-step-document", bpt_id=bpt.bpt_id, pdt_id=pdt.pdt_id)
