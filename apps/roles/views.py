from django.shortcuts import render
from django.views import View
from rest_framework.viewsets import ModelViewSet

from apps.users.ui_permissions import LoginRequiredRoleMixin
from apps.users.permissions import RoleBasedPermission
from .models import Roles
from .serializers import RoleSerializer


class AdminOnlyPermission(RoleBasedPermission):
    allowed_roles = {"ADMIN"}


class RoleViewSet(ModelViewSet):
    queryset = Roles.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [AdminOnlyPermission]


class UIRoleListView(LoginRequiredRoleMixin, View):
    allowed_roles = {"ADMIN"}

    def get(self, request):
        return render(request, "ui/admin/roles.html", {"roles": Roles.objects.all()})
