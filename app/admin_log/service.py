"""Бизнес-логика admin-audit-log модуля.

`log_action` намеренно НЕ делает commit — вызывающий сервис коммитит сам.
Это даёт транзакционную инвариантность: если бизнес-операция упадёт после
flush'а лога, общий rollback откатит обе записи. Так мы не повторяем Go-баг
«бизнес-успех ⇄ лог-провал» (там запись была fire-and-forget).
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import Admin
from app.admin_log.constants import AdminAction, EntityType
from app.admin_log.models import AdminLogs


async def log_action(
    db: AsyncSession,
    *,
    admin_id: int,
    action: AdminAction,
    entity_type: EntityType,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AdminLogs:
    now = datetime.now(UTC)
    log = AdminLogs(
        admin_id=admin_id,
        action=action.value,
        entity_type=entity_type.value,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
        created_at=now,
        updated_at=now,
    )
    db.add(log)
    await db.flush()
    return log


async def _attach_admin_info(db: AsyncSession, logs: list[AdminLogs]) -> list[dict[str, Any]]:
    if not logs:
        return []
    admin_ids = {log.admin_id for log in logs}
    stmt = select(Admin.id, Admin.name, Admin.email).where(Admin.id.in_(admin_ids))
    rows = (await db.execute(stmt)).all()
    admin_map = {row.id: (row.name, row.email) for row in rows}
    result: list[dict[str, Any]] = []
    for log in logs:
        name, email = admin_map.get(log.admin_id, (None, None))
        result.append(
            {
                "id": log.id,
                "admin_id": log.admin_id,
                "admin_name": name,
                "admin_email": email,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": log.created_at,
            }
        )
    return result


async def list_logs(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    admin_id_filter: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    base = select(AdminLogs).where(AdminLogs.deleted_at.is_(None))
    count_stmt = select(func.count()).select_from(AdminLogs).where(AdminLogs.deleted_at.is_(None))
    if admin_id_filter is not None:
        base = base.where(AdminLogs.admin_id == admin_id_filter)
        count_stmt = count_stmt.where(AdminLogs.admin_id == admin_id_filter)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        base.order_by(AdminLogs.created_at.desc(), AdminLogs.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = list((await db.execute(stmt)).scalars().all())
    items = await _attach_admin_info(db, logs)
    return items, int(total)
