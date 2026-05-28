from apps.logs.models import OperationLog
from apps.processes.models import ProcessSteps


def write_operation_log(*, user, operation_result, document=None, step=None):
    if step is None and document is not None:
        step = ProcessSteps.objects.filter(process_id=document.process_id).order_by("step_order").first()
    return OperationLog.objects.create(
        user_id=user,
        document_id=document,
        step_id=step,
        operation_result=operation_result,
    )
