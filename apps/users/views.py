from django.shortcuts import redirect, render
from django.views import View
from rest_framework import status
from django.contrib.auth.hashers import check_password
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.logs.services import write_operation_log
from apps.logs.models import OperationLog
from apps.roles.views import AdminOnlyPermission
from .ui_permissions import LoginRequiredRoleMixin
from apps.roles.models import Roles
from apps.documents.models import Documents
from apps.templates_cfg.models import DocumentTypes
from apps.requisites.models import RequisiteLinks, Requisites
from .models import Users
from .permissions import get_request_user
from .serializers import AuthSerializer, UserSerializer


class UserViewSet(ModelViewSet):
    queryset = Users.objects.select_related("role_id").all()
    serializer_class = UserSerializer
    permission_classes = [AdminOnlyPermission]

    def perform_create(self, serializer):
        user = serializer.save()
        write_operation_log(user=user, operation_result=f"USER_CREATED:{user.login}")


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        write_operation_log(user=user, operation_result=f"REGISTER:{user.login}")
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login = serializer.validated_data["login"]
        password = serializer.validated_data["password"]
        user = Users.objects.filter(login=login).select_related("role_id").first()
        valid = bool(user and ((user.password_hash and check_password(password, user.password_hash)) or user.password == password))
        if not valid:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        request.session["user_id"] = user.user_id
        write_operation_log(user=user, operation_result=f"LOGIN:{user.login}")
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        user = get_request_user(request)
        if user:
            write_operation_log(user=user, operation_result=f"LOGOUT:{user.login}")
        request.session.pop("user_id", None)
        return Response({"ok": True})


class CurrentUserView(APIView):
    def get(self, request):
        user = get_request_user(request)
        if not user:
            return Response({"user": None})
        return Response(UserSerializer(user).data)


class RegisterPageView(View):
    def get(self, request):
        return render(request, "ui/auth/register.html", {"roles": Roles.objects.all()})

    def post(self, request):
        roles = Roles.objects.all()
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")
        field_errors = {}
        if password != password_confirm:
            field_errors["password_confirm"] = "Пароли не совпадают"
            return render(request, "ui/auth/register.html", {"roles": roles, "field_errors": field_errors})
        payload = {
            "login": request.POST.get("login", "").strip(),
            "full_name": request.POST.get("full_name", "").strip(),
            "password": password,
            "role_id": request.POST.get("role_id"),
        }
        serializer = UserSerializer(data=payload)
        if not serializer.is_valid():
            for key, errors in serializer.errors.items():
                field_errors[key] = errors[0]
            return render(request, "ui/auth/register.html", {"roles": roles, "field_errors": field_errors})
        user = serializer.save()
        write_operation_log(user=user, operation_result=f"REGISTER:{user.login}")
        return redirect("login-page")


class LoginPageView(View):
    def get(self, request):
        return render(request, "ui/auth/login.html")

    def post(self, request):
        login = request.POST.get("login", "").strip()
        password = request.POST.get("password", "")
        user = Users.objects.filter(login=login).select_related("role_id").first()
        valid = bool(user and ((user.password_hash and check_password(password, user.password_hash)) or user.password == password))
        if not valid:
            return render(request, "ui/auth/login.html", {"field_errors": {"password": "Неверный логин или пароль"}})
        request.session["user_id"] = user.user_id
        write_operation_log(user=user, operation_result=f"LOGIN:{user.login}")
        return redirect("dashboard")


class LogoutPageView(View):
    def get(self, request):
        user = get_request_user(request)
        if user:
            write_operation_log(user=user, operation_result=f"LOGOUT:{user.login}")
        request.session.pop("user_id", None)
        return redirect("login-page")


class ProfilePageView(View):
    def get(self, request):
        user = get_request_user(request)
        if not user:
            return redirect("login-page")
        role_actions = {
            "ADMIN": ["Управление пользователями", "Управление ролями", "Просмотр журнала"],
            "SPECIALIST": ["Настройка шаблонов", "Настройка реквизитов", "Настройка процессов"],
            "OPERATOR": ["Создание документов", "Заполнение переменных полей", "Просмотр предпросмотра"],
        }
        return render(
            request,
            "ui/auth/profile.html",
            {"profile_user": user, "actions": role_actions.get(user.role_id.role_name, [])},
        )


class DashboardView(View):
    def get(self, request):
        user = get_request_user(request)
        if not user:
            return redirect("login-page")
        role_name = user.role_id.role_name
        stats = {}
        if role_name == "ADMIN":
            stats = {
                "Пользователей": Users.objects.count(),
                "Документов": Documents.objects.count(),
                "Шаблонов": DocumentTypes.objects.count(),
                "Операций в журнале": OperationLog.objects.count(),
            }
            cards = [
                {"title": "Пользователи", "url": "/ui/users/"},
                {"title": "Роли", "url": "/ui/roles/"},
                {"title": "Журнал операций", "url": "/ui/logs/"},
                {"title": "Все документы", "url": "/ui/documents/"},
            ]
            return render(request, "ui/dashboard.html", {"cards": cards, "stats": stats, "role_name": role_name})
        if role_name == "SPECIALIST":
            stats = {
                "Типов документов": DocumentTypes.objects.count(),
                "Реквизитов": Requisites.objects.count(),
                "Связей реквизитов": RequisiteLinks.objects.count(),
            }
            cards = [
                {"title": "Шаблоны БП", "url": "/ui/bpm/process-templates/"},
                {"title": "Справочники", "url": "/ui/bpm/dictionaries/"},
                {"title": "Типы документов", "url": "/ui/document-types/"},
                {"title": "Загрузить Word-шаблон", "url": "/ui/templates/upload/"},
                {"title": "Объекты", "url": "/ui/production-objects/"},
                {"title": "Реквизиты", "url": "/ui/requisites/"},
                {"title": "Связи реквизитов", "url": "/ui/requisite-links/"},
                {"title": "Бизнес-процессы", "url": "/ui/processes/"},
                {"title": "Этапы процессов", "url": "/ui/process-steps/"},
            ]
            return render(request, "ui/dashboard.html", {"cards": cards, "stats": stats, "role_name": role_name})
        stats = {
            "Создано документов": Documents.objects.filter(user_id=user).count(),
            "Черновиков": Documents.objects.filter(user_id=user, status="draft").count(),
            "Сформированных": Documents.objects.filter(user_id=user, status="generated").count(),
        }
        cards = [
            {"title": "Экземпляры БП", "url": "/ui/bpm/run/"},
            {"title": "Мои документы", "url": "/ui/documents/"},
            {"title": "Сформированные документы", "url": "/ui/documents/?status=generated"},
        ]
        return render(request, "ui/dashboard.html", {"cards": cards, "stats": stats, "role_name": role_name})


class UIUserListView(View):
    def get(self, request):
        user = get_request_user(request)
        if not user or user.role_id.role_name != "ADMIN":
            return redirect("dashboard")
        users = Users.objects.select_related("role_id").all()
        return render(request, "ui/admin/users.html", {"users": users})


class HelpPageView(View):
    def get(self, request):
        user = get_request_user(request)
        if not user:
            return redirect("login-page")
        return render(request, "ui/help.html")


class UISystemStyleguideView(LoginRequiredRoleMixin, View):
    """Служебная страница: все визуальные стили интерфейса (для разработки и согласования)."""

    allowed_roles = {"ADMIN", "SPECIALIST", "OPERATOR"}

    def get(self, request):
        return render(request, "ui/system/styleguide.html")
