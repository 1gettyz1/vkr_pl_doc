import io
import json
import zipfile

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from apps.documents.services import generate_document as doc_generate
from apps.logs.services import write_operation_log
from apps.processes.models import Processes
from apps.requisites.models import RequisiteValues, Requisites
from apps.templates_cfg.models import DocumentTypes, ProductionObjects
from apps.templates_cfg.views import sync_doc_type_table_fields_after_docx_upload
from apps.users.ui_permissions import LoginRequiredRoleMixin

from .models import (
    BusinessProcessInstance,
    BusinessProcessTemplate,
    DictionaryColumn,
    DictionaryRecord,
    FieldSourceRule,
    InstanceDictionarySelection,
    ProcessDocumentInstance,
    ProcessDocumentTemplate,
    ReferenceDictionary,
)
from .rule_help import rule_summary_line
from .services import (
    dictionaries_for_operator_startup,
    get_or_create_document_for_step,
    resolve_fields_for_step,
    resolve_objects_dictionary_id,
)


def _wizard_table_ui_context(document, payload):
    """JSON для UI таблицы и подстановка первой строки в поля-столбцы."""
    dt = document.document_type_id
    if not getattr(dt, "has_table_template", False):
        return {"has_table": False, "table_columns_json": "[]", "table_rows_json": "[]"}
    table_cols = [f for f in payload["fields"] if f.get("table_column")]
    meta = [
        {
            "requisite_id": f["requisite_id"],
            "name": f["name"],
            "placeholder_key": f.get("placeholder_key") or "",
            "is_required": f["is_required"],
            "data_type": f["data_type"],
        }
        for f in table_cols
    ]
    try:
        trows = json.loads(document.table_rows_json or "[]")
    except json.JSONDecodeError:
        trows = []
    if not isinstance(trows, list):
        trows = []
    if not trows:
        trows = [{}]
    if trows and isinstance(trows[0], dict):
        row0 = trows[0]
        for f in payload["fields"]:
            if f.get("table_column"):
                pk = f.get("placeholder_key") or ""
                if pk and pk in row0 and not (f.get("value") or "").strip():
                    f["value"] = str(row0.get(pk, "") or "")
    return {
        "has_table": True,
        "table_columns_json": json.dumps(meta, ensure_ascii=False),
        "table_rows_json": document.table_rows_json or json.dumps(trows, ensure_ascii=False),
    }


def _ensure_production_object_from_selections(selection_records: dict, bpt: BusinessProcessTemplate):
    if not selection_records:
        raise ValueError("empty_selections")
    records_list = list(selection_records.values())
    obj_dict_id = resolve_objects_dictionary_id(bpt, records_list)
    rec_obj = selection_records.get(obj_dict_id) if obj_dict_id else None
    if not rec_obj:
        rec_obj = records_list[0]
    payload = rec_obj.payload()
    po, _ = ProductionObjects.objects.update_or_create(
        source_record=rec_obj,
        defaults={
            "name": str(payload.get("name") or rec_obj.lookup_key)[:255],
            "object_type": str(payload.get("object_type") or "Объект")[:255],
        },
    )
    return po


def _fallback_production_object_when_no_dicts():
    po, _ = ProductionObjects.objects.get_or_create(
        name="— БП без привязки к справочнику —",
        defaults={"object_type": "Служебный"},
    )
    return po


def _zip_instance_documents_response(request, inst: BusinessProcessInstance) -> HttpResponse:
    slots = (
        ProcessDocumentInstance.objects.filter(business_process_instance=inst)
        .select_related("document", "process_document_template__document_type")
        .order_by("process_document_template__step_order")
    )
    buf = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for slot in slots:
            doc = slot.document
            if not doc.generated_file:
                try:
                    doc_generate(doc, [], request.enterprise_user)
                    doc.refresh_from_db()
                except ValueError:
                    continue
            if not doc.generated_file or not doc.generated_file.name:
                continue
            try:
                with doc.generated_file.open("rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            dt_name = slot.process_document_template.document_type.name
            base = f"{slot.process_document_template.step_order:02d}_{dt_name}"
            safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in base).strip() or "document"
            fname = f"{safe}.docx"
            n = 1
            while fname in used_names:
                fname = f"{safe}_{n}.docx"
                n += 1
            used_names.add(fname)
            zf.writestr(fname, data)
    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="bpm_{inst.bpi_id}_documents.zip"'
    return resp


class SpecialistBPMPermission:
    allowed_roles = {"ADMIN", "SPECIALIST"}


class OperatorBPMPermission:
    allowed_roles = {"ADMIN", "OPERATOR"}


class UIBPMProcessTemplateListView(LoginRequiredRoleMixin, View):
    allowed_roles = SpecialistBPMPermission.allowed_roles

    def get(self, request):
        items = BusinessProcessTemplate.objects.select_related("legacy_process", "objects_dictionary").all()
        return render(
            request,
            "ui/bpm/specialist/process_template_list.html",
            {"templates": items},
        )

    def post(self, request):
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if not name:
            return redirect("ui-bpm-process-templates")
        process = Processes.objects.create(
            name=f"Процесс: {name}",
            description=description or "",
        )
        bpt = BusinessProcessTemplate.objects.create(
            name=name,
            description=description,
            legacy_process=process,
        )
        write_operation_log(
            user=request.enterprise_user,
            operation_result=f"Создан шаблон БП «{bpt.name}» (служебный процесс «{process.name}»).",
        )
        return redirect("ui-bpm-process-templates")


class UIBPMProcessTemplateDetailView(LoginRequiredRoleMixin, View):
    allowed_roles = SpecialistBPMPermission.allowed_roles

    def get(self, request, bpt_id):
        bpt = get_object_or_404(
            BusinessProcessTemplate.objects.select_related("legacy_process", "objects_dictionary"),
            bpt_id=bpt_id,
        )
        steps = (
            ProcessDocumentTemplate.objects.filter(business_process_template=bpt)
            .select_related("document_type")
            .order_by("step_order")
        )
        doc_types_with_template = (
            DocumentTypes.objects.exclude(Q(template_file__isnull=True) | Q(template_file="")).order_by("name")
        )
        return render(
            request,
            "ui/bpm/specialist/process_template_detail.html",
            {
                "bpt": bpt,
                "steps": steps,
                "doc_types_with_template": doc_types_with_template,
            },
        )

    def post(self, request, bpt_id):
        bpt = get_object_or_404(BusinessProcessTemplate, bpt_id=bpt_id)
        action = request.POST.get("action", "add_step")
        if action == "update_meta":
            bpt.name = request.POST.get("name", bpt.name).strip() or bpt.name
            bpt.description = request.POST.get("description", "").strip()
            bpt.save(update_fields=["name", "description"])
            write_operation_log(
                user=request.enterprise_user,
                operation_result=f"Обновлены название и описание шаблона БП «{bpt.name}».",
            )
            return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)
        if action == "delete_step":
            pdt = ProcessDocumentTemplate.objects.get(
                pdt_id=request.POST["pdt_id"],
                business_process_template=bpt,
            )
            write_operation_log(user=request.enterprise_user, operation_result=f"BPM_STEP_DELETED:{pdt.name}")
            pdt.delete()
            return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)
        if action == "delete_template":
            write_operation_log(user=request.enterprise_user, operation_result=f"BPM_TEMPLATE_DELETED:{bpt.name}")
            bpt.delete()
            return redirect("ui-bpm-process-templates")
        if action == "add_step_docx":
            step_order = int(request.POST.get("step_order") or 1)
            step_name = request.POST.get("step_name", "").strip() or f"Шаг {step_order}"
            title = request.POST.get("new_doc_type_name", "").strip()
            description = request.POST.get("new_doc_type_description", "").strip()
            upload = request.FILES.get("template_file")
            if title and upload:
                if DocumentTypes.objects.filter(name__iexact=title).exists():
                    write_operation_log(
                        user=request.enterprise_user,
                        operation_result=f"Тип документа «{title}» уже существует — этап не создан.",
                    )
                else:
                    has_table = request.POST.get("has_table_template") == "on"
                    dt = DocumentTypes.objects.create(name=title, description=description, template_file=upload)
                    err = sync_doc_type_table_fields_after_docx_upload(dt, has_table)
                    if err:
                        dt.delete()
                        write_operation_log(
                            user=request.enterprise_user,
                            operation_result=f"Ошибка загрузки DOCX для этапа: {err}",
                        )
                        return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)
                    ProcessDocumentTemplate.objects.update_or_create(
                        business_process_template=bpt,
                        step_order=step_order,
                        defaults={"name": step_name, "document_type": dt},
                    )
                    write_operation_log(
                        user=request.enterprise_user,
                        operation_result=f"Добавлен этап «{step_name}» с новым типом документа «{title}» и DOCX.",
                    )
            return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)
        step_order = int(request.POST.get("step_order") or 1)
        name = request.POST.get("step_name", "").strip() or f"Шаг {step_order}"
        document_type_id = request.POST.get("document_type_id")
        if document_type_id:
            dt = DocumentTypes.objects.get(document_type_id=document_type_id)
            if not dt.template_file or str(dt.template_file).strip() == "":
                write_operation_log(
                    user=request.enterprise_user,
                    operation_result=f"Этап не добавлен: у типа «{dt.name}» нет загруженного DOCX.",
                )
                return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)
            ProcessDocumentTemplate.objects.update_or_create(
                business_process_template=bpt,
                step_order=step_order,
                defaults={"name": name, "document_type": dt},
            )
            write_operation_log(user=request.enterprise_user, operation_result=f"BPM_STEP_UPSERT:{name}")
        return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)


class UIBPMFieldRulesView(LoginRequiredRoleMixin, View):
    allowed_roles = SpecialistBPMPermission.allowed_roles

    def get(self, request, bpt_id, pdt_id):
        bpt = get_object_or_404(BusinessProcessTemplate, bpt_id=bpt_id)
        pdt = get_object_or_404(
            ProcessDocumentTemplate.objects.select_related("document_type"),
            pdt_id=pdt_id,
            business_process_template=bpt,
        )
        requisites = Requisites.objects.filter(document_type_id=pdt.document_type).order_by("requisite_id")
        rule_by_req = {r.requisite_id: r for r in FieldSourceRule.objects.filter(process_document_template=pdt)}
        rows = []
        for req in requisites:
            rule = rule_by_req.get(req.requisite_id)
            rows.append(
                {
                    "req": req,
                    "rule": rule,
                    "summary": rule_summary_line(pdt, req, rule),
                }
            )
        dictionaries = ReferenceDictionary.objects.prefetch_related("records").all()
        dict_keys = {}
        for d in dictionaries:
            cols = list(DictionaryColumn.objects.filter(dictionary=d).order_by("sort_order", "key"))
            if cols:
                dict_keys[str(d.dictionary_id)] = [
                    {"key": c.key, "label": (c.title or c.key).strip() or c.key} for c in cols
                ]
            else:
                keys = set()
                for rec in d.records.all():
                    keys.update(rec.payload().keys())
                dict_keys[str(d.dictionary_id)] = [
                    {"key": k, "label": k} for k in sorted(keys)
                ]
        other_steps = (
            ProcessDocumentTemplate.objects.filter(business_process_template=bpt)
            .exclude(pdt_id=pdt.pdt_id)
            .order_by("step_order")
        )
        pdt_req_map = {}
        for opdt in ProcessDocumentTemplate.objects.filter(business_process_template=bpt).select_related("document_type"):
            pdt_req_map[str(opdt.pdt_id)] = [
                {"id": r.requisite_id, "label": f"{r.name} ({r.placeholder_key})"}
                for r in Requisites.objects.filter(document_type_id=opdt.document_type).order_by("name")
            ]
        dict_samples = {}
        for d in dictionaries:
            fr = d.records.first()
            dict_samples[str(d.dictionary_id)] = fr.payload() if fr else {}
        return render(
            request,
            "ui/bpm/specialist/field_rules.html",
            {
                "bpt": bpt,
                "pdt": pdt,
                "rows": rows,
                "dictionaries": dictionaries,
                "other_steps": other_steps,
                "source_types": (
                    (FieldSourceRule.SOURCE_MANUAL, "Ручной ввод"),
                    (FieldSourceRule.SOURCE_DICTIONARY, "Справочник"),
                    (FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT, "Предыдущий документ"),
                ),
                "dict_keys_json": json.dumps(dict_keys, ensure_ascii=False),
                "pdt_requisites_json": json.dumps(pdt_req_map, ensure_ascii=False),
                "dict_samples_json": json.dumps(dict_samples, ensure_ascii=False),
            },
        )

    def post(self, request, bpt_id, pdt_id):
        bpt = get_object_or_404(BusinessProcessTemplate, bpt_id=bpt_id)
        pdt = get_object_or_404(ProcessDocumentTemplate, pdt_id=pdt_id, business_process_template=bpt)
        for req in Requisites.objects.filter(document_type_id=pdt.document_type):
            prefix = f"rule_{req.requisite_id}_"
            st = request.POST.get(f"{prefix}source_type", FieldSourceRule.SOURCE_MANUAL)
            if st not in (
                FieldSourceRule.SOURCE_MANUAL,
                FieldSourceRule.SOURCE_DICTIONARY,
                FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT,
            ):
                st = FieldSourceRule.SOURCE_MANUAL
            dict_id = request.POST.get(f"{prefix}dictionary_id")
            spdt_id = request.POST.get(f"{prefix}source_pdt_id")
            srq_id = request.POST.get(f"{prefix}source_req_id")
            did = int(dict_id) if dict_id and st == FieldSourceRule.SOURCE_DICTIONARY else None
            dfield = (
                request.POST.get(f"{prefix}dictionary_field", "").strip()
                if st == FieldSourceRule.SOURCE_DICTIONARY
                else ""
            )
            spdt = (
                int(spdt_id)
                if spdt_id and st == FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT
                else None
            )
            srq = (
                int(srq_id)
                if srq_id and st == FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT
                else None
            )
            FieldSourceRule.objects.update_or_create(
                process_document_template=pdt,
                requisite=req,
                defaults={
                    "source_type": st,
                    "dictionary_id": did,
                    "dictionary_field": dfield,
                    "object_field": "",
                    "context_key": "",
                    "source_process_document_template_id": spdt,
                    "source_requisite_id": srq,
                },
            )
        write_operation_log(user=request.enterprise_user, operation_result=f"BPM_FIELD_RULES_SAVED:{pdt.name}")
        return redirect("ui-bpm-process-template-detail", bpt_id=bpt.bpt_id)


class UIBPMOperatorHubView(LoginRequiredRoleMixin, View):
    allowed_roles = OperatorBPMPermission.allowed_roles

    def get(self, request):
        templates = BusinessProcessTemplate.objects.select_related("legacy_process").all()
        instances = (
            BusinessProcessInstance.objects.filter(user=request.enterprise_user)
            .select_related("business_process_template", "production_object")
            .order_by("-created_at")[:50]
        )
        return render(
            request,
            "ui/bpm/operator/hub.html",
            {"templates": templates, "instances": instances},
        )


class UIBPMStartInstanceView(LoginRequiredRoleMixin, View):
    allowed_roles = OperatorBPMPermission.allowed_roles

    def get(self, request, bpt_id):
        bpt = get_object_or_404(BusinessProcessTemplate.objects.select_related("objects_dictionary"), bpt_id=bpt_id)
        required_dicts = list(dictionaries_for_operator_startup(bpt))
        return render(
            request,
            "ui/bpm/operator/start_instance.html",
            {
                "bpt": bpt,
                "required_dicts": required_dicts,
                "instance_name": "",
            },
        )

    def post(self, request, bpt_id):
        bpt = get_object_or_404(BusinessProcessTemplate.objects.select_related("objects_dictionary"), bpt_id=bpt_id)
        required_dicts = list(dictionaries_for_operator_startup(bpt))
        instance_name = (request.POST.get("instance_name", "") or "").strip()[:255]
        selection_records = {}
        missing = []
        for d in required_dicts:
            rid = request.POST.get(f"selection_dict_{d.dictionary_id}", "").strip()
            if not rid:
                missing.append(d.name)
                continue
            selection_records[d.dictionary_id] = DictionaryRecord.objects.select_related("dictionary").get(
                record_id=int(rid),
                dictionary_id=d.dictionary_id,
            )
        if missing:
            return render(
                request,
                "ui/bpm/operator/start_instance.html",
                {
                    "bpt": bpt,
                    "required_dicts": required_dicts,
                    "error": "Выберите запись для: " + ", ".join(missing),
                    "instance_name": instance_name,
                },
            )

        if not required_dicts:
            po = _fallback_production_object_when_no_dicts()
        else:
            try:
                po = _ensure_production_object_from_selections(selection_records, bpt)
            except ValueError:
                return render(
                    request,
                    "ui/bpm/operator/start_instance.html",
                    {
                        "bpt": bpt,
                        "required_dicts": required_dicts,
                        "error": "Не удалось определить объект по выбранным справочникам — проверьте настройку шаблона БП.",
                        "instance_name": instance_name,
                    },
                )

        ctx_raw = request.POST.get("context_json", "").strip()
        try:
            ctx = json.loads(ctx_raw) if ctx_raw else {}
        except json.JSONDecodeError:
            ctx = {}

        first_rec = next(iter(selection_records.values()), None)
        lookup = (first_rec.lookup_key if first_rec else "")[:255]

        inst = BusinessProcessInstance.objects.create(
            instance_name=instance_name,
            business_process_template=bpt,
            user=request.enterprise_user,
            production_object=po,
            legacy_process=bpt.legacy_process,
            dictionary_lookup_key=lookup,
            dictionary_record=first_rec,
            context_json=json.dumps(ctx, ensure_ascii=False),
            status=BusinessProcessInstance.STATUS_IN_PROGRESS,
            current_step_order=1,
        )
        for rec in selection_records.values():
            InstanceDictionarySelection.objects.create(
                business_process_instance=inst,
                dictionary=rec.dictionary,
                record=rec,
            )

        user_name = request.enterprise_user.full_name
        sel_txt = (
            "; ".join(f"«{r.dictionary.name}»: {r.lookup_key}" for r in selection_records.values())
            if selection_records
            else "без выбора справочников (поля на шагах)"
        )
        write_operation_log(
            user=request.enterprise_user,
            document=None,
            operation_result=(
                f"Оператор {user_name} запустил БП «{bpt.name}» для объекта «{po.name}». Выборы: {sel_txt}."
            ),
        )
        return redirect("ui-bpm-instance-wizard", bpi_id=inst.bpi_id)


class UIBPMInstanceWizardView(LoginRequiredRoleMixin, View):
    allowed_roles = OperatorBPMPermission.allowed_roles

    def get(self, request, bpi_id):
        inst = get_object_or_404(
            BusinessProcessInstance.objects.select_related(
                "business_process_template",
                "production_object",
                "legacy_process",
                "dictionary_record",
                "dictionary_record__dictionary",
            ),
            bpi_id=bpi_id,
        )
        if inst.user_id != request.enterprise_user.user_id and request.enterprise_user.role_id.role_name != "ADMIN":
            return redirect("ui-bpm-operator-hub")
        steps = list(
            ProcessDocumentTemplate.objects.filter(business_process_template=inst.business_process_template).order_by(
                "step_order"
            )
        )
        if not steps:
            return render(request, "ui/bpm/operator/wizard_empty.html", {"inst": inst})
        order = inst.current_step_order
        pdt = get_object_or_404(ProcessDocumentTemplate, business_process_template=inst.business_process_template, step_order=order)
        slot, document = get_or_create_document_for_step(inst, pdt, log_user=request.enterprise_user)
        payload = resolve_fields_for_step(inst, pdt, request.enterprise_user)
        current_values = {
            rv.requisite_id_id: rv.value
            for rv in RequisiteValues.objects.filter(document_id=document)
        }
        for f in payload["fields"]:
            if f["requisite_id"] in current_values:
                f["value"] = current_values[f["requisite_id"]]
        ctx_extra = _wizard_table_ui_context(document, payload)
        sel_parts = []
        for s in InstanceDictionarySelection.objects.filter(business_process_instance=inst).select_related(
            "dictionary", "record"
        ):
            sel_parts.append(f"{s.dictionary.name} — {s.record.lookup_key}")
        dict_labels_join = "; ".join(sel_parts) if sel_parts else "—"
        return render(
            request,
            "ui/bpm/operator/wizard_step.html",
            {
                "inst": inst,
                "steps": steps,
                "pdt": pdt,
                "document": document,
                "fields": payload["fields"],
                "warnings": payload["warnings"],
                "step_index": order,
                "total_steps": len(steps),
                "dict_record_label": dict_labels_join,
                **ctx_extra,
            },
        )

    def post(self, request, bpi_id):
        inst = get_object_or_404(
            BusinessProcessInstance.objects.select_related("dictionary_record", "dictionary_record__dictionary"),
            bpi_id=bpi_id,
        )
        if inst.user_id != request.enterprise_user.user_id and request.enterprise_user.role_id.role_name != "ADMIN":
            return redirect("ui-bpm-operator-hub")
        steps = list(
            ProcessDocumentTemplate.objects.filter(business_process_template=inst.business_process_template).order_by(
                "step_order"
            )
        )
        order = inst.current_step_order
        pdt = get_object_or_404(ProcessDocumentTemplate, business_process_template=inst.business_process_template, step_order=order)
        _, document = get_or_create_document_for_step(inst, pdt)
        payload = resolve_fields_for_step(inst, pdt, request.enterprise_user)
        field_map = {f["requisite_id"]: f for f in payload["fields"]}
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
                rid = int(key.replace("req_", ""))
                meta = field_map.get(rid, {})
                if meta.get("table_column"):
                    continue
                val = (value or "").strip()
                if meta.get("field_kind") == "constant" and not val:
                    val = meta.get("value", "")
                RequisiteValues.objects.update_or_create(
                    document_id=document,
                    requisite_id_id=rid,
                    defaults={"value": val},
                )
        action = request.POST.get("wizard_action", "save")
        if action == "save":
            write_operation_log(
                user=request.enterprise_user,
                document=document,
                operation_result=(
                    f'Сохранены значения документа «{pdt.document_type.name}» на шаге «{pdt.name}».'
                ),
            )
        elif action == "next":
            max_order = max(s.step_order for s in steps) if steps else 1
            if order < max_order:
                inst.current_step_order = order + 1
                inst.save(update_fields=["current_step_order"])
                write_operation_log(
                    user=request.enterprise_user,
                    document=document,
                    operation_result=(
                        f"Переход к следующему шагу БП «{inst.business_process_template.name}» "
                        f"(с шага {order} на {inst.current_step_order})."
                    ),
                )
            else:
                for s in steps:
                    _, doc_step = get_or_create_document_for_step(inst, s)
                    try:
                        doc_generate(doc_step, [], request.enterprise_user)
                    except ValueError:
                        pass
                write_operation_log(
                    user=request.enterprise_user,
                    document=document,
                    operation_result=(
                        f'Сформированы DOCX по всем шагам. Завершён экземпляр БП «{inst.business_process_template.name}».'
                    ),
                )
                inst.status = BusinessProcessInstance.STATUS_COMPLETED
                inst.save(update_fields=["status"])
                return _zip_instance_documents_response(request, inst)
        elif action == "prev" and order > 1:
            inst.current_step_order = order - 1
            inst.save(update_fields=["current_step_order"])
            write_operation_log(
                user=request.enterprise_user,
                document=document,
                operation_result=f"Возврат на предыдущий шаг экземпляра БП «{inst.business_process_template.name}».",
            )
        elif action == "generate":
            try:
                doc_generate(document, [], request.enterprise_user)
                write_operation_log(
                    user=request.enterprise_user,
                    document=document,
                    operation_result=f'Повторно сформирован DOCX для «{pdt.document_type.name}».',
                )
            except ValueError as e:
                ctx_extra = _wizard_table_ui_context(document, payload)
                return render(
                    request,
                    "ui/bpm/operator/wizard_step.html",
                    {
                        "inst": inst,
                        "steps": steps,
                        "pdt": pdt,
                        "document": document,
                        "fields": payload["fields"],
                        "warnings": payload["warnings"] + [str(e)],
                        "step_index": order,
                        "total_steps": len(steps),
                        "error": str(e),
                        "dict_record_label": "; ".join(
                            f"{s.dictionary.name} — {s.record.lookup_key}"
                            for s in InstanceDictionarySelection.objects.filter(
                                business_process_instance=inst
                            ).select_related("dictionary", "record")
                        )
                        or "—",
                        **ctx_extra,
                    },
                )
        return redirect("ui-bpm-instance-wizard", bpi_id=inst.bpi_id)


class UIBPMInstanceDownloadAllView(LoginRequiredRoleMixin, View):
    allowed_roles = OperatorBPMPermission.allowed_roles

    def get(self, request, bpi_id):
        inst = get_object_or_404(BusinessProcessInstance, bpi_id=bpi_id)
        if inst.user_id != request.enterprise_user.user_id and request.enterprise_user.role_id.role_name != "ADMIN":
            return redirect("ui-bpm-operator-hub")
        if inst.status != BusinessProcessInstance.STATUS_COMPLETED:
            return redirect("ui-bpm-instance-wizard", bpi_id=inst.bpi_id)
        write_operation_log(
            user=request.enterprise_user,
            operation_result=f"Скачан архив DOCX экземпляра БП №{inst.bpi_id}.",
        )
        return _zip_instance_documents_response(request, inst)
