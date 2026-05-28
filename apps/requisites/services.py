from datetime import datetime

import json

from apps.documents.models import Documents
from apps.requisites.models import RequisiteLinks, Requisites, RequisiteValues


TYPE_VALIDATORS = {
    "text": lambda _: True,
    "number": lambda v: _is_float(v),
    "boolean": lambda v: str(v).lower() in {"true", "false", "1", "0"},
    "select": lambda v: str(v).strip() != "",
    "date": lambda v: _is_date(v),
}


def _is_float(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _is_date(value):
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def validate_document_requisites(document):
    dt = document.document_type_id
    requisites = Requisites.objects.filter(document_type_id=dt)
    if getattr(dt, "has_table_template", False):
        try:
            rows = json.loads(document.table_rows_json or "[]")
        except json.JSONDecodeError:
            rows = []
        if not isinstance(rows, list):
            rows = []
        table_reqs = [r for r in requisites if r.is_table_column and r.placeholder_key]
        non_table_reqs = [r for r in requisites if not r.is_table_column]
        errors = []
        if not rows and any(r.is_required for r in table_reqs):
            errors.append("Добавьте хотя бы одну строку таблицы и заполните обязательные поля.")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"Строка таблицы {i + 1}: неверный формат данных.")
                continue
            for req in table_reqs:
                if req.is_required:
                    val = row.get(req.placeholder_key, "")
                    if val is None or str(val).strip() == "":
                        errors.append(f"Строка {i + 1}: не заполнено обязательное поле «{req.name}».")
                elif req.placeholder_key in row and row[req.placeholder_key] not in (None, ""):
                    validator = TYPE_VALIDATORS.get(req.data_type, TYPE_VALIDATORS["text"])
                    if not validator(row.get(req.placeholder_key, "")):
                        errors.append(f"Строка {i + 1}: поле «{req.name}» — неверный тип ({req.data_type}).")
        existing = {rv.requisite_id_id: rv.value for rv in RequisiteValues.objects.filter(document_id=document)}
        for req in non_table_reqs:
            value = existing.get(req.requisite_id)
            if req.is_required and (value is None or value == ""):
                errors.append(f"Required field '{req.name}' is empty")
                continue
            if value:
                validator = TYPE_VALIDATORS.get(req.data_type, TYPE_VALIDATORS["text"])
                if not validator(value):
                    errors.append(f"Field '{req.name}' has invalid type {req.data_type}")
        return errors

    existing = {rv.requisite_id_id: rv.value for rv in RequisiteValues.objects.filter(document_id=document)}
    errors = []
    for req in requisites:
        value = existing.get(req.requisite_id)
        if req.is_required and (value is None or value == ""):
            errors.append(f"Required field '{req.name}' is empty")
            continue
        if value:
            validator = TYPE_VALIDATORS.get(req.data_type, TYPE_VALIDATORS["text"])
            if not validator(value):
                errors.append(f"Field '{req.name}' has invalid type {req.data_type}")
    return errors


def _apply_rule(current_value, inherited_value, rule):
    if inherited_value is None or inherited_value == "":
        return current_value
    if rule == "always_override":
        return inherited_value
    if rule == "copy_if_empty" and (current_value is None or current_value == ""):
        return inherited_value
    if rule == "copy_latest_value":
        return inherited_value
    if rule == "append_unique":
        if current_value and inherited_value in current_value:
            return current_value
        return f"{current_value}; {inherited_value}" if current_value else inherited_value
    return current_value


class DocumentAutofillService:
    def __init__(self, *, document_type_id, process_id, object_id, user_id=None):
        self.document_type_id = document_type_id
        self.process_id = process_id
        self.object_id = object_id
        self.user_id = user_id

    def _latest_source_value(self, source_requisite_id):
        source_docs = Documents.objects.filter(
            process_id_id=self.process_id,
            object_id_id=self.object_id,
        ).order_by("-created_at")
        value = (
            RequisiteValues.objects.filter(
                document_id__in=source_docs,
                requisite_id_id=source_requisite_id,
            )
            .exclude(value="")
            .order_by("-document_id__created_at")
            .first()
        )
        return value.value if value else None

    def build_form_payload(self):
        requisites = Requisites.objects.filter(document_type_id_id=self.document_type_id).order_by("requisite_id")
        links = {
            link.target_requisite_id_id: link
            for link in RequisiteLinks.objects.select_related("source_requisite_id", "target_requisite_id").filter(
                target_requisite_id__in=requisites
            )
        }
        payload = []
        warnings = []
        for req in requisites:
            value = ""
            source = "manual"
            readonly = False
            link = links.get(req.requisite_id)
            if link:
                inherited = self._latest_source_value(link.source_requisite_id_id)
                if inherited not in (None, ""):
                    value = _apply_rule("", inherited, link.inheritance_rule) or ""
                    source = f"auto:{link.source_requisite_id.name}"
                    readonly = req.field_kind == "constant"
                elif req.field_kind == "constant":
                    warnings.append(
                        f"Поле '{req.name}' не было найдено в связанных документах. "
                        f"Заполните вручную или проверьте настройки связей."
                    )
            payload.append(
                {
                    "requisite_id": req.requisite_id,
                    "name": req.name,
                    "data_type": req.data_type,
                    "is_required": req.is_required,
                    "field_kind": req.field_kind,
                    "value": value,
                    "source": source,
                    "readonly": readonly,
                }
            )
        return {"fields": payload, "warnings": warnings}
