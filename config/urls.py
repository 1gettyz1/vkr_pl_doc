from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter

from apps.documents.views import (
    DocumentGenerationView,
    DocumentViewSet,
    UICreateDocumentView,
    UIDocumentDownloadView,
    UIDocumentListView,
    UIDocumentPreviewView,
    UILogsView,
    UIProcessesView,
    UIProcessStepsView,
    UIDocumentImportView,
    UIRequisitesView,
    UIRequisiteLinksView,
    UIRequisiteFormView,
)
from apps.logs.views import OperationLogViewSet
from apps.processes.views import ProcessStepViewSet, ProcessViewSet
from apps.requisites.views import AutofillView, RequisiteLinkViewSet, RequisiteValueViewSet, RequisiteViewSet
from apps.roles.views import RoleViewSet, UIRoleListView
from apps.bpm.dictionary_pages import (
    DictionaryRecordsSearchJsonView,
    UIDictionaryCreateView,
    UIDictionaryDetailView,
    UIDictionaryHomeView,
)
from apps.bpm.step_views import UIBPMStepDocumentView
from apps.bpm.views import (
    UIBPMFieldRulesView,
    UIBPMInstanceDownloadAllView,
    UIBPMInstanceWizardView,
    UIBPMOperatorHubView,
    UIBPMProcessTemplateDetailView,
    UIBPMProcessTemplateListView,
    UIBPMStartInstanceView,
)
from apps.templates_cfg.views import (
    DocumentTypeViewSet,
    ProductionObjectViewSet,
    UIDocumentTypeCrudView,
    UIProductionObjectsView,
    UITemplateConfigureFieldsView,
    UITemplateCreateView,
    UITemplateListView,
    UITemplatePreviewView,
)
from apps.users.views import (
    CurrentUserView,
    DashboardView,
    HelpPageView,
    UISystemStyleguideView,
    LoginPageView,
    LoginView,
    LogoutPageView,
    LogoutView,
    ProfilePageView,
    RegisterPageView,
    RegisterView,
    UIUserListView,
    UserViewSet,
)

router = DefaultRouter()
router.register("roles", RoleViewSet)
router.register("users", UserViewSet)
router.register("document-types", DocumentTypeViewSet)
router.register("production-objects", ProductionObjectViewSet)
router.register("requisites", RequisiteViewSet)
router.register("requisite-values", RequisiteValueViewSet)
router.register("requisite-links", RequisiteLinkViewSet)
router.register("processes", ProcessViewSet)
router.register("process-steps", ProcessStepViewSet)
router.register("documents", DocumentViewSet)
router.register("logs", OperationLogViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/documents/<int:document_id>/generate/", DocumentGenerationView.as_view()),
    path("api/documents/autofill/", AutofillView.as_view()),
    path("api/auth/register/", RegisterView.as_view()),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/me/", CurrentUserView.as_view()),
    path("", DashboardView.as_view(), name="dashboard"),
    path("dashboard/", DashboardView.as_view(), name="dashboard-page"),
    path("login/", LoginPageView.as_view(), name="login-page"),
    path("register/", RegisterPageView.as_view(), name="register-page"),
    path("logout/", LogoutPageView.as_view(), name="logout-page"),
    path("profile/", ProfilePageView.as_view(), name="profile-page"),
    path("ui/help/", HelpPageView.as_view(), name="ui-help"),
    path("ui/system/styleguide/", UISystemStyleguideView.as_view(), name="ui-system-styleguide"),
    path("ui/users/", UIUserListView.as_view(), name="ui-users"),
    path("ui/roles/", UIRoleListView.as_view(), name="ui-roles"),
    path("ui/documents/", UIDocumentListView.as_view(), name="ui-documents"),
    path("ui/documents/new/", UICreateDocumentView.as_view(), name="ui-create-document"),
    path("ui/documents/create/", UICreateDocumentView.as_view(), name="ui-documents-create"),
    path("ui/documents/<int:document_id>/requisites/", UIRequisiteFormView.as_view(), name="ui-requisites"),
    path("ui/documents/<int:document_id>/preview/", UIDocumentPreviewView.as_view(), name="ui-document-preview"),
    path("ui/documents/<int:document_id>/download/", UIDocumentDownloadView.as_view(), name="ui-document-download"),
    path("ui/documents/import/", UIDocumentImportView.as_view(), name="ui-document-import"),
    path("ui/templates/", UITemplateListView.as_view(), name="ui-templates"),
    path("ui/document-types/", UIDocumentTypeCrudView.as_view(), name="ui-document-types"),
    path("ui/production-objects/", UIProductionObjectsView.as_view(), name="ui-production-objects"),
    path("ui/templates/create/", UITemplateCreateView.as_view(), name="ui-template-create"),
    path("ui/templates/upload/", UITemplateCreateView.as_view(), name="ui-template-upload"),
    path("ui/templates/<int:document_type_id>/configure/", UITemplateConfigureFieldsView.as_view(), name="ui-template-configure"),
    path("ui/templates/<int:document_type_id>/preview/", UITemplatePreviewView.as_view(), name="ui-template-preview"),
    path("ui/requisite-links/", UIRequisiteLinksView.as_view(), name="ui-requisite-links"),
    path("ui/requisites/", UIRequisitesView.as_view(), name="ui-requisites-list"),
    path("ui/processes/", UIProcessesView.as_view(), name="ui-processes"),
    path("ui/process-steps/", UIProcessStepsView.as_view(), name="ui-process-steps"),
    path("ui/logs/", UILogsView.as_view(), name="ui-logs"),
    path("ui/bpm/process-templates/", UIBPMProcessTemplateListView.as_view(), name="ui-bpm-process-templates"),
    path("ui/bpm/process-templates/<int:bpt_id>/", UIBPMProcessTemplateDetailView.as_view(), name="ui-bpm-process-template-detail"),
    path(
        "ui/bpm/process-templates/<int:bpt_id>/steps/<int:pdt_id>/rules/",
        UIBPMFieldRulesView.as_view(),
        name="ui-bpm-field-rules",
    ),
    path(
        "ui/bpm/process-templates/<int:bpt_id>/steps/<int:pdt_id>/document/",
        UIBPMStepDocumentView.as_view(),
        name="ui-bpm-step-document",
    ),
    path("ui/bpm/dictionaries/", UIDictionaryHomeView.as_view(), name="ui-bpm-dictionaries"),
    path("ui/bpm/dictionaries/create/", UIDictionaryCreateView.as_view(), name="ui-bpm-dictionary-create"),
    path("ui/bpm/dictionaries/<int:dictionary_id>/", UIDictionaryDetailView.as_view(), name="ui-bpm-dictionary-detail"),
    path(
        "ui/bpm/api/dictionaries/<int:dictionary_id>/records/search/",
        DictionaryRecordsSearchJsonView.as_view(),
        name="ui-bpm-dictionary-records-search",
    ),
    path("ui/bpm/run/", UIBPMOperatorHubView.as_view(), name="ui-bpm-operator-hub"),
    path("ui/bpm/run/<int:bpt_id>/start/", UIBPMStartInstanceView.as_view(), name="ui-bpm-start-instance"),
    path("ui/bpm/instance/<int:bpi_id>/", UIBPMInstanceWizardView.as_view(), name="ui-bpm-instance-wizard"),
    path(
        "ui/bpm/instance/<int:bpi_id>/download-all/",
        UIBPMInstanceDownloadAllView.as_view(),
        name="ui-bpm-instance-download-all",
    ),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
