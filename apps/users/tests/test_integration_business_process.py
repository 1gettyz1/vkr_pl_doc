"""
Интеграционный тест полного сценария: пользователь → БП → документ → реквизиты → журнал.

Запуск:
  python manage.py test apps.users.tests.test_integration_business_process
"""
from django.test import TestCase

from apps.bpm.models import BusinessProcessInstance, BusinessProcessTemplate
from apps.documents.models import Documents
from apps.logs.services import write_operation_log
from apps.processes.models import Processes, ProcessSteps
from apps.requisites.models import RequisiteValues, Requisites
from apps.roles.models import Roles
from apps.templates_cfg.models import DocumentTypes, ProductionObjects
from apps.users.models import Users
from apps.users.serializers import UserSerializer


class FullBusinessProcessIntegrationTest(TestCase):
    """Сквозной сценарий с проверкой связей между сущностями."""

    def test_full_business_process_scenario(self):
        # 1–2. Роль и пользователь
        role = Roles.objects.create(
            role_name="INTEGRATION_OPERATOR",
            description="роль для интеграционного теста",
        )
        ser = UserSerializer(
            data={
                "login": "integration_bp_user",
                "full_name": "Оператор интеграции",
                "password": "integration_secret_1",
                "role_id": role.role_id,
            }
        )
        ser.is_valid(raise_exception=True)
        user = ser.save()
        user = Users.objects.select_related("role_id").get(pk=user.pk)
        self.assertEqual(user.role_id_id, role.role_id)

        # 3. Производственный объект (обязателен для Documents и BusinessProcessInstance)
        production_object = ProductionObjects.objects.create(
            object_type="Участок",
            name="Участок сборки №1",
        )

        # 4. Базовый процесс
        process = Processes.objects.create(
            name="Интеграционный процесс",
            description="процесс для сквозного теста",
        )

        # 5. Шаблон бизнес-процесса (требует Processes)
        bpt = BusinessProcessTemplate.objects.create(
            name="Интеграционный шаблон БП",
            description="описание шаблона",
            legacy_process=process,
        )
        self.assertEqual(bpt.legacy_process_id, process.process_id)

        # 6. Экземпляр бизнес-процесса
        bpi = BusinessProcessInstance.objects.create(
            instance_name="Экземпляр для дипломного теста",
            business_process_template=bpt,
            user=user,
            production_object=production_object,
            legacy_process=process,
        )
        self.assertEqual(bpi.business_process_template_id, bpt.bpt_id)
        self.assertEqual(bpi.user_id, user.user_id)
        self.assertEqual(bpi.production_object_id, production_object.object_id)
        self.assertEqual(bpi.legacy_process_id, process.process_id)

        # 7. Тип документа
        doc_type = DocumentTypes.objects.create(
            name="Акт интеграционного приёмки",
            description="тип для теста",
        )

        # 8. Документ (все обязательные FK: тип, объект, пользователь, процесс)
        document = Documents.objects.create(
            document_type_id=doc_type,
            object_id=production_object,
            user_id=user,
            process_id=process,
            status="draft",
        )
        self.assertEqual(document.document_type_id_id, doc_type.document_type_id)
        self.assertEqual(document.object_id_id, production_object.object_id)
        self.assertEqual(document.user_id_id, user.user_id)
        self.assertEqual(document.process_id_id, process.process_id)

        # Шаг процесса — чтобы write_operation_log смог связать лог с шагом при передаче document
        step = ProcessSteps.objects.create(
            name="Подписание",
            step_order=1,
            process_id=process,
        )

        # 9–10. Реквизит и значение
        requisite = Requisites.objects.create(
            name="Номер акта",
            document_type_id=doc_type,
            data_type="text",
            field_kind="variable",
            placeholder_key="act_number",
            is_required=True,
        )
        self.assertEqual(requisite.document_type_id_id, doc_type.document_type_id)

        req_value = RequisiteValues.objects.create(
            document_id=document,
            requisite_id=requisite,
            value="АКТ-2026-INT-01",
        )
        self.assertEqual(req_value.document_id_id, document.document_id)
        self.assertEqual(req_value.requisite_id_id, requisite.requisite_id)

        # 11. Журнал операций (через сервис проекта)
        log = write_operation_log(
            user=user,
            document=document,
            operation_result="INTEGRATION_TEST: документ создан в рамках экземпляра БП",
        )
        self.assertEqual(log.user_id_id, user.user_id)
        self.assertEqual(log.document_id_id, document.document_id)
        self.assertEqual(log.step_id_id, step.step_id)

        # 12. Связность цепочки (BPI → пользователь/шаблон/объект; документ → тот же объект и процесс)
        self.assertEqual(bpi.user_id, user.user_id)
        self.assertEqual(document.user_id, user)
        self.assertEqual(document.object_id, production_object)
        self.assertEqual(bpi.production_object, production_object)
        self.assertEqual(document.process_id, process)
        self.assertEqual(bpt.legacy_process, process)
        self.assertEqual(bpi.business_process_template, bpt)
        self.assertTrue(
            RequisiteValues.objects.filter(
                document_id=document,
                requisite_id=requisite,
            ).exists()
        )
