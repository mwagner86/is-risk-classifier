from typing import TYPE_CHECKING, Any

from apps.audit.models import AuditAction, AuditEntry
from apps.core.models import BaseModel

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.risks.models import Risk


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def record(
    *,
    actor: "User | None",
    action: AuditAction,
    obj: BaseModel,
    risk: "Risk | None" = None,
    field: str = "",
    old: Any = None,
    new: Any = None,
) -> AuditEntry:
    return AuditEntry.objects.create(
        actor=actor,
        action=action,
        risk=risk,
        object_type=type(obj).__name__,
        object_id=obj.pk,
        field=field,
        old_value=_text(old),
        new_value=_text(new),
    )
