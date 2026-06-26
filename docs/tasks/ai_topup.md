# ТЗ: Admin-сторона докупки AI-запросов (модуль `ai_topup`)

**Версия:** 1.0
**Дата:** 2026-05-22
**Статус:** Ready
**Связанный сервис:** `server/` (Go) — user-side уже реализован (`POST /ai-topup/requests`, `GET /ai-topup/requests/my`, `GET /restaurants/:id/ai-stats/limit`).

---

## 1. Контекст

Пользователь (владелец/staff с правом) подаёт заявку на докупку пакета AI-запросов сверх месячного лимита `MonthlyAIRequestLimit = 25000`. Заявка лежит в БД со статусом `pending`. Цена и размер пакета — snapshot из конфига `server/[ai_topup]` на момент создания.

**Admin-сторона должна:**
1. Показывать список и детали заявок с фильтрами.
2. **Approve** — атомарно перевести заявку в `approved` и создать запись `ai_request_quotas`, которая до конца календарного месяца суммируется в эффективный лимит ресторана (точка чтения — `quota_repository.GetActiveTotal` в `server/`).
3. **Reject** — перевести заявку в `rejected` с комментарием админа, без выдачи квоты.

Ходим в **общую БД** напрямую (тот же DSN), как уже делает `app/subscriptions/` с `SubscriptionExtensionRequests`. Никаких HTTP-вызовов в `server/`.

### 1.1 Предусловия в БД

Таблицы `ai_request_top_up_requests` и `ai_request_quotas` уже созданы в `server/migrations/0012_add_ai_topup.up.sql`. Полная схема:

**`ai_request_top_up_requests`** (заявка):
| Колонка | Тип | Примечание |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `created_at`, `updated_at`, `deleted_at` | TIMESTAMPTZ | gorm.Model |
| `organization_id` | BIGINT NOT NULL → `organizations.id` (CASCADE) | |
| `restaurant_id` | BIGINT NOT NULL → `restaurants.id` (CASCADE) | |
| `user_id` | BIGINT NOT NULL → `users.id` | |
| `name`, `phone`, `email` | TEXT NOT NULL | контакт |
| `packs_count` | INT NOT NULL, CHECK > 0 | сколько пакетов |
| `requests_per_pack` | BIGINT NOT NULL, CHECK > 0 | snapshot из конфига |
| `price_per_pack` | NUMERIC(12,2) NOT NULL, CHECK ≥ 0 | snapshot |
| `currency` | TEXT NOT NULL | snapshot |
| `total_price` | NUMERIC(14,2) NOT NULL, CHECK ≥ 0 | `packs_count * price_per_pack` |
| `comment` | TEXT NOT NULL DEFAULT '' | от пользователя |
| `status` | TEXT NOT NULL DEFAULT 'pending' | `pending`/`approved`/`rejected` |
| `admin_comment` | TEXT NOT NULL DEFAULT '' | заполняем при approve/reject |
| `processed_at` | TIMESTAMPTZ NULL | момент approve/reject |

**`ai_request_quotas`** (выданная квота):
| Колонка | Тип | Примечание |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `created_at`, `updated_at`, `deleted_at` | TIMESTAMPTZ | gorm.Model |
| `restaurant_id` | BIGINT NOT NULL → `restaurants.id` (CASCADE) | |
| `top_up_request_id` | BIGINT NOT NULL → `ai_request_top_up_requests.id` (RESTRICT) | |
| `requests_granted` | BIGINT NOT NULL, CHECK > 0 | `packs_count * requests_per_pack` |
| `period_start` | TIMESTAMPTZ NOT NULL | момент approve |
| `expires_at` | TIMESTAMPTZ NOT NULL | начало след. календарного месяца от `period_start` |

Индекс `idx_ai_quotas_active(restaurant_id, expires_at)` уже есть — `quota_repository.GetActiveTotal` под него заточен.

---

## 2. Затронутые файлы

| Файл | Действие |
|------|----------|
| `app/ai_topup/__init__.py` | Создать (пустой) |
| `app/ai_topup/constants.py` | Создать (enum `AITopUpRequestStatus`) |
| `app/ai_topup/exceptions.py` | Создать (`TopUpRequestNotFound`, `TopUpRequestNotPending`) |
| `app/ai_topup/schemas.py` | Создать (Request/Response Pydantic, все наследуют `CamelModel`) |
| `app/ai_topup/service.py` | Создать (list/get/approve/reject + хелпер `start_of_next_month`) |
| `app/ai_topup/router.py` | Создать (4 endpoint'а под `CurrentAdmin`) |
| `app/ai_topup/helpers.py` | Создать (вынести `start_of_next_month`, `validate_no_null_bytes` импортом) |
| `app/models.py` | Добавить SQLAlchemy-модели `AIRequestTopUpRequests`, `AIRequestQuotas` |
| `app/admin_log/constants.py` | В `EntityType` добавить `AI_TOPUP_REQUEST = "ai_topup_request"` |
| `app/main.py` (или там где `include_router`) | Подключить `ai_topup_router` |
| `alembic/env.py` | Импорт модели не нужен — таблицы создаёт `server/` миграцией. Только если поднимаем in-memory SQLite для тестов — модели в `app/models.py` уже подтянутся через `Base` |
| `tests/ai_topup/__init__.py` | Создать |
| `tests/ai_topup/conftest.py` | Создать (фикстуры заявки и админа) |
| `tests/ai_topup/test_router.py` | Создать (list/get/approve/reject + concurrency + audit) |

**Что НЕ трогаем:**
- `server/` (Go) — user-side уже готов, schema не меняется.
- `alembic/versions/*` — миграцию создавать **не нужно**, таблицы под Go-миграциями.

---

## 3. Требования

### 3.1 SQLAlchemy-модели (`app/models.py`)

Зеркало Go-моделей, точные имена колонок. Используем `Base` (DeclarativeBase), `Mapped`/`mapped_column` как в `SubscriptionExtensionRequests`. Связи `relationship(...)` к `Organizations`, `Restaurants`, `Users` (lazy="raise" чтобы ловить N+1).

```python
class AIRequestTopUpRequests(Base):
    __tablename__ = "ai_request_top_up_requests"
    __table_args__ = (
        ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                             name="fk_ai_topup_org"),
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"],
                             name="fk_ai_topup_restaurant"),
        ForeignKeyConstraint(["user_id"], ["users.id"],
                             name="fk_ai_topup_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    packs_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_per_pack: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price_per_pack: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    admin_comment: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organizations"] = relationship(lazy="raise")
    restaurant: Mapped["Restaurants"] = relationship(lazy="raise")
    user: Mapped["Users"] = relationship(lazy="raise")


class AIRequestQuotas(Base):
    __tablename__ = "ai_request_quotas"
    __table_args__ = (
        ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"],
                             name="fk_ai_quota_restaurant"),
        ForeignKeyConstraint(["top_up_request_id"], ["ai_request_top_up_requests.id"],
                             name="fk_ai_quota_request"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    restaurant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    top_up_request_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    requests_granted: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

### 3.2 Enum + exceptions

`app/ai_topup/constants.py`:
```python
from enum import StrEnum

class AITopUpRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
```

`app/ai_topup/exceptions.py` (паттерн повторяет `app/subscriptions/exceptions.py`, помечаем `@final`):
```python
from typing import final
from fastapi import status
from app.exceptions import AppException

@final
class TopUpRequestNotFound(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "top-up request not found"

@final
class TopUpRequestNotPending(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "top-up request is not in pending status"
```

`app/admin_log/constants.py` — добавить enum-значение:
```python
class EntityType(StrEnum):
    ...
    AI_TOPUP_REQUEST = "ai_topup_request"
```

### 3.3 Pydantic-схемы (`app/ai_topup/schemas.py`)

Все response-схемы наследуют `CamelModel` (из `app/schemas.py`). У `CamelModel` уже выставлены `alias_generator=to_camel`, `populate_by_name=True`, `from_attributes=True`, `serialize_by_alias=True` — то есть поля в коде snake_case, в JSON camelCase, и `model_validate(orm_obj)` работает напрямую с SQLAlchemy-объектом.

**Контракт типов с user-side:** в Go (`server/`) денежные поля отдаются как JSON-`number` (`float64`). Чтобы фронту не пришлось различать формат между двумя бэками, в Pydantic-схемах используем `float` (не `Decimal` — он сериализуется в строку). В SQLAlchemy-моделях остаётся `Numeric(12,2)`/`Numeric(14,2)` для корректной точности хранения; конвертация `Decimal → float` происходит автоматически в Pydantic v2.

```python
from datetime import datetime
from pydantic import Field
from app.schemas import CamelModel
from app.ai_topup.constants import AITopUpRequestStatus


class OrganizationShort(CamelModel):
    id: int
    name: str

class UserShort(CamelModel):
    id: int
    name: str
    email: str

class TopUpRequestResp(CamelModel):
    id: int
    organization: OrganizationShort
    restaurant_id: int            # отдаём только id — отдельной модели Restaurant не делаем
    user: UserShort
    name: str
    phone: str
    email: str
    packs_count: int
    requests_per_pack: int
    price_per_pack: float         # snapshot цены пакета (см. контракт типов выше)
    currency: str
    total_price: float            # packs_count * price_per_pack
    comment: str
    status: AITopUpRequestStatus
    admin_comment: str
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime

class QuotaResp(CamelModel):
    id: int
    restaurant_id: int
    top_up_request_id: int
    requests_granted: int
    period_start: datetime
    expires_at: datetime
    created_at: datetime

class ApproveTopUpRequestReq(CamelModel):
    admin_comment: str = Field(default="", max_length=2000)

class RejectTopUpRequestReq(CamelModel):
    admin_comment: str = Field(default="", max_length=2000)

class ApproveTopUpResp(CamelModel):
    top_up_request: TopUpRequestResp
    quota: QuotaResp
```

### 3.4 Helper: расчёт `expires_at`

`app/ai_topup/helpers.py`:
```python
from datetime import datetime, timezone

def start_of_next_month(now: datetime) -> datetime:
    """Начало следующего календарного месяца относительно now (в UTC).

    Используется для expires_at квоты: «квота сгорает в конце месяца».
    Если approve 31 мая в 23:00 UTC → 2026-06-01 00:00:00+00:00.
    Если approve 28 декабря → 2027-01-01 00:00:00+00:00.
    """
    tz = now.tzinfo or timezone.utc
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=tz)
    return datetime(now.year, now.month + 1, 1, tzinfo=tz)
```

**Переиспользуемые хелперы** (живут в `app/subscriptions/helpers.py`, импортировать оттуда):
- `now_utc() -> datetime` — `datetime.now(timezone.utc)`, фиксируется один раз на транзакцию.
- `validate_no_null_bytes(s: str | None) -> None` — защита от 0x00 в строковых полях (PostgreSQL TEXT этого не любит).

Можно вынести в `app/common/helpers.py` отдельным шагом, но это **out of scope** этой задачи — оставляем импорты из `subscriptions.helpers`.

### 3.5 Service (`app/ai_topup/service.py`)

Точно повторяем паттерны `app/subscriptions/service.py`:
- `now_utc()` берётся один раз на транзакцию.
- Audit-лог пишется **перед `db.commit()`** в той же транзакции — упадёт бизнес-логика, откатится и лог.
- Для approve/reject — `SELECT ... FOR UPDATE` на заявке (`_get_request_loaded(..., for_update=True)`) защищает от double-approve.
- Soft-deleted (`deleted_at IS NOT NULL`) скрыты везде.

**Internal helpers, которые нужно написать** (по паттерну `_get_extension_request_loaded` + `_request_to_resp` из `subscriptions/service.py`):

```python
async def _get_request_loaded(
    db: AsyncSession, req_id: int, *, for_update: bool = False
) -> AIRequestTopUpRequests:
    """Заявка с eager-loaded organization+user; 404 если нет/soft-deleted."""
    stmt = (
        select(AIRequestTopUpRequests)
        .options(
            selectinload(AIRequestTopUpRequests.organization),
            selectinload(AIRequestTopUpRequests.user),
        )
        .where(
            AIRequestTopUpRequests.id == req_id,
            AIRequestTopUpRequests.deleted_at.is_(None),
        )
    )
    if for_update:
        stmt = stmt.with_for_update()
    req = (await db.scalars(stmt)).one_or_none()
    if req is None:
        raise TopUpRequestNotFound
    return req


def _request_to_resp(req: AIRequestTopUpRequests) -> TopUpRequestResp:
    """ORM → Response. Невалидный статус из БД → PENDING (defensive)."""
    try:
        status_enum = AITopUpRequestStatus(req.status or AITopUpRequestStatus.PENDING.value)
    except ValueError:
        status_enum = AITopUpRequestStatus.PENDING
    return TopUpRequestResp(
        id=int(req.id),
        organization=OrganizationShort.model_validate(req.organization),
        restaurant_id=int(req.restaurant_id),
        user=UserShort.model_validate(req.user),
        name=req.name, phone=req.phone, email=req.email,
        packs_count=int(req.packs_count),
        requests_per_pack=int(req.requests_per_pack),
        price_per_pack=float(req.price_per_pack),
        currency=req.currency,
        total_price=float(req.total_price),
        comment=req.comment,
        status=status_enum,
        admin_comment=req.admin_comment,
        processed_at=req.processed_at,
        created_at=req.created_at,
        updated_at=req.updated_at,
    )
```

**Сигнатуры:**
```python
async def list_requests(
    db: AsyncSession, *,
    status: AITopUpRequestStatus | None,
    organization_id: int | None,
    restaurant_id: int | None,
    pagination: PaginationModel,
) -> tuple[list[TopUpRequestResp], int]: ...

async def get_request(db: AsyncSession, req_id: int) -> TopUpRequestResp: ...

async def reject_request(
    db: AsyncSession, *,
    req_id: int,
    payload: RejectTopUpRequestReq,
    admin_id: int,
    client_ip: str | None,
) -> TopUpRequestResp: ...

async def approve_request(
    db: AsyncSession, *,
    req_id: int,
    payload: ApproveTopUpRequestReq,
    admin_id: int,
    client_ip: str | None,
) -> ApproveTopUpResp: ...
```

**Approve — атомарная транзакция** (все вызовы `admin_log_service.log_action` — **с keyword-args**, как в `subscriptions/service.py`):
1. `validate_no_null_bytes(payload.admin_comment)`.
2. `request = await _get_request_loaded(db, req_id, for_update=True)` — eager-load `organization`, `user`.
3. Если `request.status != AITopUpRequestStatus.PENDING.value` → `raise TopUpRequestNotPending` (400).
4. `now = now_utc()`.
5. `expires_at = start_of_next_month(now)`.
6. `requests_granted = request.packs_count * request.requests_per_pack`.
7. UPDATE заявки in-place: `request.status = "approved"`, `request.admin_comment = payload.admin_comment`, `request.processed_at = now`, `request.updated_at = now`.
8. INSERT квоты:
   ```python
   quota = AIRequestQuotas(
       restaurant_id=request.restaurant_id,
       top_up_request_id=request.id,
       requests_granted=requests_granted,
       period_start=now,
       expires_at=expires_at,
       created_at=now,
       updated_at=now,
   )
   db.add(quota)
   await db.flush()  # получить quota.id для audit
   ```
9. Audit (одной записью):
   ```python
   _ = await admin_log_service.log_action(
       db,
       admin_id=admin_id,
       action=AdminAction.UPDATE,
       entity_type=EntityType.AI_TOPUP_REQUEST,
       entity_id=int(request.id),
       details={
           "previousStatus": "pending",
           "newStatus": "approved",
           "quotaId": int(quota.id),
           "requestsGranted": requests_granted,
           "expiresAt": expires_at.isoformat(),
           "adminComment": payload.admin_comment,
       },
       ip_address=client_ip,
   )
   ```
10. `await db.commit()`.
11. `await db.refresh(request, attribute_names=["organization", "user"])`, `await db.refresh(quota)`.
12. Вернуть `ApproveTopUpResp(top_up_request=_request_to_resp(request), quota=QuotaResp.model_validate(quota))`.

**Reject — атомарная транзакция:**
1. `validate_no_null_bytes(payload.admin_comment)`.
2. `request = await _get_request_loaded(db, req_id, for_update=True)`.
3. Если `request.status != AITopUpRequestStatus.PENDING.value` → `raise TopUpRequestNotPending`.
4. `now = now_utc()`.
5. UPDATE in-place: `status="rejected"`, `admin_comment=payload.admin_comment`, `processed_at=now`, `updated_at=now`.
6. `await admin_log_service.log_action(db, admin_id=admin_id, action=AdminAction.UPDATE, entity_type=EntityType.AI_TOPUP_REQUEST, entity_id=int(request.id), details={"previousStatus":"pending","newStatus":"rejected","adminComment":payload.admin_comment}, ip_address=client_ip)`.
7. `await db.commit()`.
8. `await db.refresh(request, attribute_names=["organization", "user"])`.
9. Вернуть `_request_to_resp(request)`.

**List:**
- Default фильтр: `status=pending` (как у subscription extension requests — это очередь работы).
- Параметры: `status` (опц.), `organization_id` (опц., gt=0), `restaurant_id` (опц., gt=0).
- Сортировка: `created_at DESC, id DESC`.
- Пагинация: `PaginationParams` из `app/common/utils/pagination.py` (defaults: `limit=10` (ge=1, le=100), `offset=0` (ge=0)).
- Eager-load: `selectinload(AIRequestTopUpRequests.organization)`, `selectinload(AIRequestTopUpRequests.user)`.
- Total для пагинации — `select(func.count()).select_from(AIRequestTopUpRequests).where(and_(*filters))` отдельным запросом (паттерн `list_extension_requests`).

### 3.6 Router (`app/ai_topup/router.py`)

```python
router = APIRouter(prefix="/ai-topup/requests", tags=["ai-topup"])

@router.get("", ...)
async def list_top_up_requests(
    _admin: CurrentAdmin,
    db: DbSession,
    pagination: PaginationParams,
    status_filter: Annotated[AITopUpRequestStatus | None, Query(alias="status")] = AITopUpRequestStatus.PENDING,
    organization_id: Annotated[int | None, Query(alias="organizationId", gt=0)] = None,
    restaurant_id: Annotated[int | None, Query(alias="restaurantId", gt=0)] = None,
) -> Envelope[PaginatedResponse[TopUpRequestResp]]: ...

@router.get("/{req_id}", ...)
async def get_top_up_request(req_id: int, _admin: CurrentAdmin, db: DbSession) -> Envelope[TopUpRequestResp]: ...

@router.post("/{req_id}/approve", ...)
async def approve_top_up_request(
    req_id: int,
    body: ApproveTopUpRequestReq,
    admin: CurrentAdmin,
    db: DbSession,
    client_ip: ClientIp,
) -> Envelope[ApproveTopUpResp]: ...

@router.post("/{req_id}/reject", ...)
async def reject_top_up_request(...) -> Envelope[TopUpRequestResp]: ...
```

Подключить в `app/main.py` рядом с другими `include_router(...)` — префикс берётся из settings (как у всех остальных роутеров, не литерал):
```python
from app.ai_topup.router import router as ai_topup_router
...
app.include_router(ai_topup_router, prefix=settings.app.api_v1_prefix)
```

### 3.7 Аудит-лог (детали `details` JSONB)

Запись `admin_logs` пишется одним вызовом `admin_log_service.log_action` **перед** `db.commit()` (атомарно).

| Действие | `entity_type` | `action` | Содержимое `details` |
|---|---|---|---|
| approve | `ai_topup_request` | `update` | `{previousStatus, newStatus:"approved", quotaId, requestsGranted, expiresAt, adminComment}` |
| reject | `ai_topup_request` | `update` | `{previousStatus, newStatus:"rejected", adminComment}` |

### 3.8 Concurrency

- `_get_request_loaded(..., for_update=True)` — `SELECT ... FOR UPDATE` на строке заявки. Два параллельных approve одной и той же заявки **сериализуются**: второй увидит уже `approved` и получит 400 (`TopUpRequestNotPending`).
- На уровне `ai_request_quotas` дополнительная защита **не нужна**: уникального ключа `(top_up_request_id)` нет (хотя по бизнес-логике одна квота на заявку — это нормально, потому что approve атомарен с проверкой статуса).

---

## 4. Ограничения

- **НЕ** менять схему БД миграцией Alembic. Таблицы под Go-миграциями `server/migrations/0012_*`. Любые правки колонок — через Go-миграции и согласование с user-side.
- **НЕ** изменять snapshot-поля (`packs_count`, `requests_per_pack`, `price_per_pack`, `currency`, `total_price`) при approve/reject — это исторические данные.
- **НЕ** создавать quota при reject. **НЕ** создавать quota при approve дважды для одной заявки (защищено идемпотентностью статуса pending).
- **НЕ** отдавать soft-deleted записи (`deleted_at IS NOT NULL`) — фильтр обязателен во всех list/get.
- **НЕ** ходить в `server/` через REST — работаем напрямую в общую БД, как уже делает `subscriptions/`.
- **НЕ** добавлять admin-операции в `server/` (Go) — там только user-side.
- При создании файлов **обязательно вызвать** `Skill(skill="fastapi-best-practices")` перед написанием кода (правило `admin_panel_global_server/CLAUDE.md`).

---

## 5. Тесты (`tests/ai_topup/`)

Pytest + httpx async client + in-memory SQLite (`aiosqlite`) как в `tests/subscriptions/`. Pydantic-схемы валидируют форму ответа.

**Минимум:**

| Тест | Что проверяет |
|---|---|
| `test_list_default_pending_only` | Без `?status` возвращаются только pending |
| `test_list_filter_by_status` | `?status=approved` отдаёт только approved |
| `test_list_filter_by_organization` | `?organizationId=N` сужает |
| `test_list_filter_by_restaurant` | `?restaurantId=N` сужает |
| `test_list_hides_soft_deleted` | Запись с `deleted_at != NULL` не попадает в выдачу |
| `test_get_by_id_happy_path` | 200 + корректные поля |
| `test_get_unknown_returns_404` | `TopUpRequestNotFound` → 404 |
| `test_get_soft_deleted_returns_404` | Soft-deleted скрыт |
| `test_approve_happy_path` | Статус → approved, processed_at, admin_comment записаны |
| `test_approve_creates_one_quota` | Ровно 1 строка в `ai_request_quotas` с правильным `requests_granted=packs*per_pack` |
| `test_approve_expires_at_is_start_of_next_month` | Approve 15-го числа → `expires_at = 1 число след. месяца 00:00 UTC` |
| `test_approve_expires_at_december_rollover` | Approve в декабре → январь след. года |
| `test_approve_double_returns_400` | Второй approve той же заявки → `TopUpRequestNotPending` 400, новых строк в `ai_request_quotas` не появилось |
| `test_approve_then_reject_returns_400` | Reject уже approved заявки → 400 |
| `test_reject_happy_path` | Статус → rejected, **квота не создаётся** |
| `test_reject_double_returns_400` | Повторный reject → 400 |
| `test_reject_does_not_touch_quotas` | После reject `count(*) FROM ai_request_quotas WHERE top_up_request_id=...` = 0 |
| `test_audit_log_written_on_approve` | В `admin_logs` появилась запись с `entity_type='ai_topup_request'`, `action='update'`, `details.quotaId == quota.id` |
| `test_audit_log_written_on_reject` | Аналогично для reject (без `quotaId` в details) |
| `test_no_auth_returns_401` | Все 4 endpoint'а без JWT → 401 |
| `test_pagination_works` | `?limit=2&offset=0` + `?offset=2` дают непересекающиеся страницы |

**E2E с user-side (опционально, отдельным маркером):** регистрация → создание заявки через `server/`-API → admin approve → `GET /restaurants/:id/ai-stats/limit` возвращает `extra == requests_granted`. Требует поднятого Go-сервера; пропускать если недоступен.

---

## 6. Критерии приёмки

- [ ] Все файлы из §2 созданы/обновлены.
- [ ] `app/ai_topup/router.py` подключён в `app/main.py` под `/api/v1`.
- [ ] `EntityType.AI_TOPUP_REQUEST` добавлен в `app/admin_log/constants.py`.
- [ ] Approve атомарно меняет статус заявки и создаёт строку `ai_request_quotas` в одной транзакции (`db.commit()` один раз).
- [ ] Audit-лог пишется **перед** `db.commit()` — гарантирована атомарность бизнес+лог (тест: симулировать ошибку до commit и убедиться что заявка не обновлена и audit не записан).
- [ ] `expires_at` = начало следующего календарного месяца от `period_start` (UTC). Случай декабря → январь след. года покрыт тестом.
- [ ] Reject не создаёт квоту.
- [ ] Double-approve / double-reject → 400 `TopUpRequestNotPending`.
- [ ] Soft-deleted записи скрыты в `list` и `get`.
- [ ] Запись в `admin_logs` пишется в той же транзакции, что и бизнес-операция.
- [ ] Все 4 endpoint'а защищены `CurrentAdmin` (401 без JWT).
- [ ] Все Response наследуют `CamelModel` (поля в JSON — camelCase).
- [ ] Все query-параметры в роутерах — `Query(alias="camelCase")`.
- [ ] `uv run pytest tests/ai_topup/ -v` — зелёный.
- [ ] `uv run ruff check .` — без ошибок.
- [ ] FastAPI swagger `/docs` корректно показывает 4 новых endpoint'а под тегом `ai-topup`.

---

## 7. Out of scope (намеренно)

- Уведомления ресторатору о результате (email/in-app) — отдельной задачей.
- Платёжный шлюз — оплата вне системы, админ подтверждает после поступления денег.
- Per-organization цены / скидки — позже, когда понадобится. Сейчас цена едина из конфига `server/[ai_topup]`.
- Отмена approve / возврат квоты — не реализуем (квота истечёт сама в конце месяца). Если потребуется — отдельная задача с soft-delete квоты + audit-запись.
- Аналитика по докупкам (сколько/на сколько за период) — добавим в `app/dashboard/` отдельно.

---

## 8. Ссылки

- User-side реализация: `server/app/module/ai_topup/`
- Точка чтения квот в `server/`: `server/app/module/ai_topup/repository/quota_repository.go::GetActiveTotal`
- Миграция: `server/migrations/0012_add_ai_topup.up.sql`
- Реализация-референс: `admin_panel_global_server/app/subscriptions/` (особенно `service.py::approve_extension_request`)
- Архитектурные конвенции: `admin_panel_global_server/CLAUDE.md` (envelope, CamelModel, audit log, concurrency)
