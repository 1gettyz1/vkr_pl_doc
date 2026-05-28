import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib.auth.hashers import make_password
from django.core.files import File
from django.core.management.base import BaseCommand
from docx import Document as DocxDocument

from apps.bpm.models import (
    BusinessProcessTemplate,
    DictionaryColumn,
    DictionaryRecord,
    FieldSourceRule,
    ProcessDocumentTemplate,
    ReferenceDictionary,
)
from apps.processes.models import ProcessSteps, Processes
from apps.requisites.models import Requisites
from apps.roles.models import Roles
from apps.templates_cfg.models import DocumentTypes, ProductionObjects
from apps.templates_cfg.views import docx_to_template_html
from apps.users.models import Users

from apps.bpm.dictionary_pages import _derive_lookup_key


class Command(BaseCommand):
    help = "Демо: два справочника с колонками, БП, объект из справочника объектов"

    def _build_demo_docx(self, lines):
        doc = DocxDocument()
        for line in lines:
            doc.add_paragraph(line)
        tmp = NamedTemporaryFile(suffix=".docx", delete=False)
        doc.save(tmp.name)
        tmp.close()
        return tmp.name

    def _add_columns(self, d: ReferenceDictionary, defs):
        """defs: list of (key, title, sort_order)"""
        for key, title, order in defs:
            DictionaryColumn.objects.get_or_create(
                dictionary=d,
                key=key,
                defaults={"title": title, "sort_order": order},
            )

    def handle(self, *args, **options):
        admin_role, _ = Roles.objects.get_or_create(role_name="ADMIN", defaults={"description": "Администратор"})
        specialist_role, _ = Roles.objects.get_or_create(
            role_name="SPECIALIST", defaults={"description": "Специалист по автоматизации"}
        )
        operator_role, _ = Roles.objects.get_or_create(role_name="OPERATOR", defaults={"description": "Оператор"})

        Users.objects.update_or_create(
            login="admin",
            defaults={
                "full_name": "Администратор",
                "password": "admin123",
                "password_hash": make_password("admin123"),
                "role_id": admin_role,
            },
        )
        Users.objects.update_or_create(
            login="specialist",
            defaults={
                "full_name": "Специалист",
                "password": "specialist123",
                "password_hash": make_password("specialist123"),
                "role_id": specialist_role,
            },
        )
        Users.objects.update_or_create(
            login="operator",
            defaults={
                "full_name": "Оператор Иванов И.И.",
                "password": "operator123",
                "password_hash": make_password("operator123"),
                "role_id": operator_role,
            },
        )

        process, _ = Processes.objects.get_or_create(
            name="Оформление служебной записки подразделения",
            defaults={"description": "Демонстрационный процесс"},
        )
        ProcessSteps.objects.update_or_create(
            process_id=process, step_order=1, defaults={"name": "Приказ"}
        )
        ProcessSteps.objects.update_or_create(
            process_id=process, step_order=2, defaults={"name": "Служебная записка"}
        )

        order_type, _ = DocumentTypes.objects.update_or_create(
            name="Приказ",
            defaults={"description": "Шаг 1 БП"},
        )
        memo_type, _ = DocumentTypes.objects.update_or_create(
            name="Служебная записка",
            defaults={"description": "Шаг 2 БП"},
        )

        order_docx_path = self._build_demo_docx(
            [
                "ПРИКАЗ",
                "Номер приказа: {{order_number}}",
                "Год: {{year}}",
                "Подразделение: {{department}}",
                "Подписант: {{signer_name}}",
            ]
        )
        memo_docx_path = self._build_demo_docx(
            [
                "СЛУЖЕБНАЯ ЗАПИСКА",
                "Подразделение: {{department}}",
                "Подписант: {{signer_name}}",
                "Должность подписанта: {{signer_position}}",
                "Год: {{year}}",
                "Тема: {{memo_topic}}",
                "Содержание: {{memo_content}}",
            ]
        )
        with open(order_docx_path, "rb") as f:
            order_type.template_file.save("order_demo.docx", File(f), save=True)
        with open(memo_docx_path, "rb") as f:
            memo_type.template_file.save("memo_demo.docx", File(f), save=True)
        Path(order_docx_path).unlink(missing_ok=True)
        Path(memo_docx_path).unlink(missing_ok=True)

        order_type.template_html = docx_to_template_html(order_type.template_file.path)
        order_type.save(update_fields=["template_html"])
        memo_type.template_html = docx_to_template_html(memo_type.template_file.path)
        memo_type.save(update_fields=["template_html"])

        req_order_num, _ = Requisites.objects.update_or_create(
            document_type_id=order_type,
            placeholder_key="order_number",
            defaults={
                "name": "Номер приказа",
                "data_type": "text",
                "is_required": True,
                "field_kind": "variable",
            },
        )
        req_order_year, _ = Requisites.objects.update_or_create(
            document_type_id=order_type,
            placeholder_key="year",
            defaults={
                "name": "Год",
                "data_type": "number",
                "is_required": True,
                "field_kind": "variable",
            },
        )
        req_order_dep, _ = Requisites.objects.update_or_create(
            document_type_id=order_type,
            placeholder_key="department",
            defaults={
                "name": "Подразделение",
                "data_type": "text",
                "is_required": True,
                "field_kind": "constant",
            },
        )
        req_order_signer, _ = Requisites.objects.update_or_create(
            document_type_id=order_type,
            placeholder_key="signer_name",
            defaults={
                "name": "Подписант",
                "data_type": "text",
                "is_required": True,
                "field_kind": "constant",
            },
        )

        req_memo_dep, _ = Requisites.objects.update_or_create(
            document_type_id=memo_type,
            placeholder_key="department",
            defaults={
                "name": "Подразделение",
                "data_type": "text",
                "is_required": True,
                "field_kind": "constant",
            },
        )
        req_memo_signer, _ = Requisites.objects.update_or_create(
            document_type_id=memo_type,
            placeholder_key="signer_name",
            defaults={
                "name": "Подписант",
                "data_type": "text",
                "is_required": True,
                "field_kind": "constant",
            },
        )
        req_memo_pos, _ = Requisites.objects.update_or_create(
            document_type_id=memo_type,
            placeholder_key="signer_position",
            defaults={
                "name": "Должность подписанта",
                "data_type": "text",
                "is_required": True,
                "field_kind": "constant",
            },
        )
        req_memo_year, _ = Requisites.objects.update_or_create(
            document_type_id=memo_type,
            placeholder_key="year",
            defaults={
                "name": "Год",
                "data_type": "number",
                "is_required": True,
                "field_kind": "constant",
            },
        )
        req_memo_topic, _ = Requisites.objects.update_or_create(
            document_type_id=memo_type,
            placeholder_key="memo_topic",
            defaults={
                "name": "Тема",
                "data_type": "text",
                "is_required": True,
                "field_kind": "variable",
            },
        )
        req_memo_content, _ = Requisites.objects.update_or_create(
            document_type_id=memo_type,
            placeholder_key="memo_content",
            defaults={
                "name": "Содержание",
                "data_type": "text",
                "is_required": True,
                "field_kind": "variable",
            },
        )

        dep_dict, _ = ReferenceDictionary.objects.get_or_create(name="Подразделения")
        self._add_columns(
            dep_dict,
            [
                ("department", "Подразделение", 1),
                ("signer_name", "Подписант", 2),
                ("signer_position", "Должность", 3),
                ("contact", "Контакт", 4),
            ],
        )
        dep_dict.selection_column_key = "department"
        dep_dict.save(update_fields=["selection_column_key"])
        dep_payload = {
            "department": "Отдел технической подготовки",
            "signer_name": "Иванов Иван Иванович",
            "signer_position": "Начальник отдела",
            "contact": "доб. 123",
        }
        dep_lk = _derive_lookup_key(dep_dict, dep_payload, None)
        DictionaryRecord.objects.update_or_create(
            dictionary=dep_dict,
            lookup_key=dep_lk,
            defaults={"payload_json": json.dumps(dep_payload, ensure_ascii=False)},
        )

        obj_dict, _ = ReferenceDictionary.objects.get_or_create(name="Объекты производства")
        self._add_columns(
            obj_dict,
            [
                ("name", "Наименование", 1),
                ("object_type", "Тип объекта", 2),
                ("dimensions", "Габариты / характеристики", 3),
                ("department_label", "Подразделение (подпись)", 4),
            ],
        )
        obj_dict.selection_column_key = "name"
        obj_dict.save(update_fields=["selection_column_key"])
        obj_payload = {
            "name": "Редуктор Р-125",
            "object_type": "Изделие",
            "dimensions": "120×80×60 мм",
            "department_label": "ОТП",
        }
        obj_lk = _derive_lookup_key(obj_dict, obj_payload, None)
        obj_rec, _ = DictionaryRecord.objects.update_or_create(
            dictionary=obj_dict,
            lookup_key=obj_lk,
            defaults={"payload_json": json.dumps(obj_payload, ensure_ascii=False)},
        )

        ProductionObjects.objects.update_or_create(
            source_record=obj_rec,
            defaults={
                "name": "Редуктор Р-125",
                "object_type": "Изделие",
            },
        )

        bpt, _ = BusinessProcessTemplate.objects.update_or_create(
            name="Оформление служебной записки подразделения",
            defaults={
                "description": "Приказ → Служебная записка; объект и подразделение из справочников",
                "legacy_process": process,
                "objects_dictionary": obj_dict,
            },
        )
        pdt_order, _ = ProcessDocumentTemplate.objects.update_or_create(
            business_process_template=bpt,
            step_order=1,
            defaults={"name": "Приказ", "document_type": order_type},
        )
        pdt_memo, _ = ProcessDocumentTemplate.objects.update_or_create(
            business_process_template=bpt,
            step_order=2,
            defaults={"name": "Служебная записка", "document_type": memo_type},
        )

        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_order,
            requisite=req_order_num,
            defaults={"source_type": FieldSourceRule.SOURCE_MANUAL},
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_order,
            requisite=req_order_year,
            defaults={"source_type": FieldSourceRule.SOURCE_MANUAL},
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_order,
            requisite=req_order_dep,
            defaults={
                "source_type": FieldSourceRule.SOURCE_DICTIONARY,
                "dictionary": dep_dict,
                "dictionary_field": "department",
            },
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_order,
            requisite=req_order_signer,
            defaults={
                "source_type": FieldSourceRule.SOURCE_DICTIONARY,
                "dictionary": dep_dict,
                "dictionary_field": "signer_name",
            },
        )

        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_memo,
            requisite=req_memo_dep,
            defaults={
                "source_type": FieldSourceRule.SOURCE_DICTIONARY,
                "dictionary": dep_dict,
                "dictionary_field": "department",
            },
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_memo,
            requisite=req_memo_signer,
            defaults={
                "source_type": FieldSourceRule.SOURCE_DICTIONARY,
                "dictionary": dep_dict,
                "dictionary_field": "signer_name",
            },
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_memo,
            requisite=req_memo_pos,
            defaults={
                "source_type": FieldSourceRule.SOURCE_DICTIONARY,
                "dictionary": dep_dict,
                "dictionary_field": "signer_position",
            },
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_memo,
            requisite=req_memo_year,
            defaults={
                "source_type": FieldSourceRule.SOURCE_PREVIOUS_DOCUMENT,
                "source_process_document_template": pdt_order,
                "source_requisite": req_order_year,
            },
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_memo,
            requisite=req_memo_topic,
            defaults={"source_type": FieldSourceRule.SOURCE_MANUAL},
        )
        FieldSourceRule.objects.update_or_create(
            process_document_template=pdt_memo,
            requisite=req_memo_content,
            defaults={"source_type": FieldSourceRule.SOURCE_MANUAL},
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Готово: справочники с колонками, БП с привязкой к справочнику объектов. "
                "operator / operator123"
            )
        )
