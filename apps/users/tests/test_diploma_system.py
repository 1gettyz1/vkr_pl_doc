"""
Короткие unit-тесты по основным сущностям системы (дипломная работа).

Запуск: python manage.py test
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.bpm.models import BusinessProcessInstance, BusinessProcessTemplate
from apps.documents.models import Documents
from apps.logs.models import OperationLog
from apps.logs.services import write_operation_log
from apps.processes.models import Processes
from apps.requisites.models import RequisiteValues, Requisites
from apps.roles.models import Roles
from apps.templates_cfg.models import DocumentTypes, ProductionObjects
from apps.users.models import Users
from apps.users.serializers import UserSerializer


class DiplomaSystemTests(TestCase):
    """Проверки моделей и API в разрезе заявленных требований."""

    def setUp(self):
        self.client = APIClient()

    def _create_role(self, name: str) -> Roles:
        return Roles.objects.create(role_name=name, description="unit test")

    def _create_user_with_password(self, login: str, role: Roles) -> Users:
        ser = UserSerializer(
            data={
                "login": login,
                "full_name": "Тестовый пользователь",
                "password": "testpass123",
                "role_id": role.role_id,
            }
        )
        ser.is_valid(raise_exception=True)
        return ser.save()

    def test_1_user_creation_and_api_login(self):
        """Создание пользователя и успешная авторизация через API."""
        role = self._create_role("DIPLOMA_TEST_ROLE_1")
        user = self._create_user_with_password("diploma_login_1", role)
        self.assertTrue(user.user_id)
        self.assertTrue(user.password_hash)

        res = self.client.post(
            "/api/auth/login/",
            {"login": "diploma_login_1", "password": "testpass123"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["login"], "diploma_login_1")

    def test_2_role_assignment(self):
        """Назначение роли пользователю (смена роли)."""
        r1 = self._create_role("DIPLOMA_ROLE_A")
        r2 = self._create_role("DIPLOMA_ROLE_B")
        user = self._create_user_with_password("diploma_user_roles", r1)
        self.assertEqual(user.role_id_id, r1.role_id)
        user.role_id = r2
        user.save(update_fields=["role_id"])
        user.refresh_from_db()
        self.assertEqual(user.role_id_id, r2.role_id)
        self.assertEqual(user.role_id.role_name, "DIPLOMA_ROLE_B")

    def test_3_business_process_template_creation(self):
        """Создание шаблона бизнес-процесса (с привязкой к процессу Processes)."""
        proc = Processes.objects.create(name="Процесс для шаблона БП", description="")
        bpt = BusinessProcessTemplate.objects.create(
            name="Шаблон БП (тест)",
            description="описание",
            legacy_process=proc,
        )
        self.assertTrue(bpt.bpt_id)
        self.assertEqual(bpt.legacy_process_id, proc.process_id)

    def test_4_business_process_instance_creation(self):
        """Создание экземпляра бизнес-процесса."""
        proc = Processes.objects.create(name="Процесс для экземпляра БП", description="")
        role = self._create_role("DIPLOMA_BPI_ROLE")
        user = self._create_user_with_password("bpi_user", role)
        bpt = BusinessProcessTemplate.objects.create(
            name="Шаблон для экземпляра",
            description="",
            legacy_process=proc,
        )
        po = ProductionObjects.objects.create(object_type="участок", name="Объект тест")
        inst = BusinessProcessInstance.objects.create(
            instance_name="Мой экземпляр",
            business_process_template=bpt,
            user=user,
            production_object=po,
            legacy_process=proc,
        )
        self.assertTrue(inst.bpi_id)
        self.assertEqual(inst.status, BusinessProcessInstance.STATUS_IN_PROGRESS)

    def test_5_document_creation(self):
        """Создание документа."""
        role = self._create_role("DIPLOMA_DOC_ROLE")
        user = self._create_user_with_password("doc_owner", role)
        proc = Processes.objects.create(name="Процесс для документа", description="")
        dt = DocumentTypes.objects.create(name="Тип документа тест", description="")
        po = ProductionObjects.objects.create(object_type="цех", name="Объект документа")
        doc = Documents.objects.create(
            document_type_id=dt,
            object_id=po,
            user_id=user,
            process_id=proc,
            status="draft",
        )
        self.assertTrue(doc.document_id)
        self.assertEqual(doc.status, "draft")

    def test_6_requisite_value_saved(self):
        """Сохранение значения реквизита для документа."""
        role = self._create_role("DIPLOMA_REQ_ROLE")
        user = self._create_user_with_password("req_user", role)
        proc = Processes.objects.create(name="Процесс реквизит", description="")
        dt = DocumentTypes.objects.create(name="Тип с реквизитом", description="")
        req = Requisites.objects.create(
            name="Номер договора",
            document_type_id=dt,
            placeholder_key="contract_no",
            data_type="text",
            field_kind="variable",
        )
        po = ProductionObjects.objects.create(object_type="объект", name="О1")
        doc = Documents.objects.create(
            document_type_id=dt,
            object_id=po,
            user_id=user,
            process_id=proc,
            status="draft",
        )
        rv = RequisiteValues.objects.create(
            document_id=doc,
            requisite_id=req,
            value="123/2026",
        )
        self.assertEqual(rv.value, "123/2026")
        self.assertEqual(
            RequisiteValues.objects.get(document_id=doc, requisite_id=req).value,
            "123/2026",
        )

    def test_7_operation_log_created(self):
        """Создание записи в журнале операций (через сервис и прямое создание)."""
        role = self._create_role("DIPLOMA_LOG_ROLE")
        user = self._create_user_with_password("log_user", role)

        log1 = write_operation_log(user=user, operation_result="TEST_OP_SERVICE")
        self.assertTrue(log1.operation_id)
        self.assertIn("TEST_OP_SERVICE", log1.operation_result)

        log2 = OperationLog.objects.create(
            user_id=user,
            operation_result="TEST_OP_DIRECT",
        )
        self.assertTrue(log2.operation_id)
        self.assertEqual(OperationLog.objects.filter(user_id=user).count(), 2)
