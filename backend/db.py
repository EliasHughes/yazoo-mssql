"""SQLAlchemy async engine + collection registry.

Supports:
- SQLite (preview/dev) via aiosqlite
- Microsoft SQL Server 2019+ (production) via aioodbc + ODBC Driver 18

Set the env var DATABASE_URL to override, otherwise falls back to a local SQLite
file at /app/backend/ylms_local.db.
"""
import os
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Iterable, Tuple

from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, DateTime, Boolean, Float,
    Index, UniqueConstraint, select, insert, update, delete, and_, or_, func, text,
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.mssql import NVARCHAR

# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL",
                              f"sqlite+aiosqlite:///{os.path.dirname(__file__)}/ylms_local.db")

_is_mssql = DATABASE_URL.startswith(("mssql", "mssql+aioodbc", "mssql+pyodbc"))
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine_kwargs: Dict[str, Any] = {"pool_pre_ping": True, "future": True}
if _is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
metadata = MetaData()

# ------------------------------------------------------------------
# Collection registry (columns extracted for indexing + query performance)
# Every other document field lives inside the JSON `data` column.
# ------------------------------------------------------------------

# Column type helpers (dialect-aware). NVARCHAR on MSSQL, TEXT on SQLite for
# unbounded strings; NVARCHAR(N) on MSSQL, VARCHAR(N) on SQLite for short.
def _short(n: int = 64):
    if _is_mssql:
        return NVARCHAR(n)
    return String(n)

def _text():
    if _is_mssql:
        return NVARCHAR("max")  # NVARCHAR(MAX)
    return Text()

def _mkcol(name: str, kind: str, unique: bool = False, index: bool = False):
    if kind == "id":
        return Column(name, _short(64), nullable=False, unique=unique, index=index)
    if kind == "code":
        return Column(name, _short(96), nullable=True, unique=unique, index=index)
    if kind == "text":
        return Column(name, _short(256), nullable=True, index=index)
    if kind == "long":
        return Column(name, _text(), nullable=True)
    if kind == "bool":
        return Column(name, Boolean, nullable=True, index=index)
    if kind == "num":
        return Column(name, Float, nullable=True, index=index)
    if kind == "int":
        return Column(name, Integer, nullable=True, index=index)
    if kind == "dt":
        # We store ISO-8601 strings for portability with Mongo-style docs.
        return Column(name, _short(40), nullable=True, index=index)
    raise ValueError(kind)


# extract_cols: list of (col_name, kind, indexed?)  — always includes id/data/code
# unique keys defined via SQLAlchemy Index/UniqueConstraint.
_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "users": {
        "extract": [("email", "text"), ("role", "text"), ("active", "bool"),
                    ("created_at", "dt")],
        "unique": ["id", "email"],
    },
    "login_attempts": {
        "extract": [("identifier", "text"), ("locked_until", "dt"), ("last_at", "dt")],
        "unique": ["identifier"],
    },
    "counters": {  # uses _id string instead of id
        "extract": [("_id_str", "text")],
        "unique": ["_id_str"],
        "id_field": "_id",
    },
    "audit_logs": {
        "extract": [("user_id", "text"), ("user_email", "text"), ("action", "text"),
                    ("module", "text"), ("entity_id", "text"), ("entity_code", "text"),
                    ("ip", "text"), ("timestamp", "dt")],
        "unique": ["id"],
    },
    "products": {
        "extract": [("code", "code"), ("name", "text"), ("type", "text"),
                    ("category", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "tests": {
        "extract": [("code", "code"), ("name", "text"), ("parameter", "text"),
                    ("method", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "reagents": {
        "extract": [("code", "code"), ("name", "text"), ("provider", "text"),
                    ("expiry_date", "dt"), ("current_stock", "num"),
                    ("min_stock", "num"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "equipment": {
        "extract": [("code", "code"), ("name", "text"), ("type", "text"),
                    ("status", "text"), ("next_calibration", "dt"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "supplies": {
        "extract": [("code", "code"), ("name", "text"), ("provider", "text"),
                    ("category", "text"), ("current_stock", "num"), ("min_stock", "num"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "samples": {
        "extract": [("code", "code"), ("product_id", "text"), ("product_name", "text"),
                    ("status", "text"), ("reception_date", "dt"), ("provider", "text"),
                    ("batch_number", "text"), ("created_at", "dt"), ("coa_number", "text")],
        "unique": ["id", "code"],
    },
    "executions": {
        "extract": [("sample_id", "text"), ("sample_code", "text"), ("test_id", "text"),
                    ("test_code", "text"), ("analyst_id", "text"),
                    ("status", "text"), ("meets_spec", "bool"),
                    ("completed_at", "dt"), ("created_at", "dt")],
        "unique": ["id"],
    },
    "batches": {
        "extract": [("code", "code"), ("sample_id", "text"), ("product_id", "text"),
                    ("status", "text"), ("coa_number", "text"),
                    ("released_at", "dt"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "coa": {
        "extract": [("coa_number", "code"), ("sample_id", "text"), ("batch_id", "text"),
                    ("product_id", "text"), ("decision", "text"),
                    ("issued_by", "text"), ("issued_at", "dt")],
        "unique": ["id", "coa_number"],
    },
    "notifications": {
        "extract": [("recipient_id", "text"), ("recipient_role", "text"),
                    ("kind", "text"), ("read", "bool"), ("priority", "text"),
                    ("entity_type", "text"), ("entity_id", "text"),
                    ("action_taken", "text"), ("created_at", "dt")],
        "unique": ["id"],
    },
    "notification_dedup": {
        "extract": [("_id_str", "text"), ("last_at", "dt")],
        "unique": ["_id_str"],
        "id_field": "_id",
    },
    "attachments": {
        "extract": [("entity_type", "text"), ("entity_id", "text"),
                    ("uploaded_by", "text"), ("uploaded_at", "dt")],
        "unique": ["id"],
    },
    "settings": {
        "extract": [("_id_str", "text")],
        "unique": ["_id_str"],
        "id_field": "_id",
    },
    "lab_form_records": {
        "extract": [("code", "code"), ("form_type", "text"), ("form_code", "text"),
                    ("status", "text"), ("linked_sample_id", "text"),
                    ("created_by", "text"), ("created_by_role", "text"),
                    ("approved_by", "text"), ("approved_at", "dt"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "user_signatures": {
        "extract": [("user_id", "text"), ("kind", "text"), ("updated_at", "dt")],
        "unique": ["id", "user_id"],
    },
    "screen_shortcuts": {
        "extract": [("shortcut", "code"), ("screen_key", "text")],
        "unique": ["id", "shortcut"],
    },
    "suppliers": {
        "extract": [("code", "code"), ("name", "text"), ("tax_id", "text"),
                    ("active", "bool"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "purchase_orders": {
        "extract": [("code", "code"), ("supplier_id", "text"), ("status", "text"),
                    ("total", "num"), ("currency", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "warehouses": {
        "extract": [("code", "code"), ("name", "text"), ("active", "bool"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "stock_movements": {
        "extract": [("code", "code"), ("type", "text"), ("item_id", "text"),
                    ("warehouse_id", "text"), ("created_at", "dt")],
        "unique": ["id"],
    },
    "production_orders": {
        "extract": [("code", "code"), ("product_id", "text"), ("status", "text"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "finance_costs": {
        "extract": [("code", "code"), ("kind", "text"), ("category", "text"),
                    ("amount", "num"), ("created_at", "dt")],
        "unique": ["id"],
    },
    "finance_kpis": {
        "extract": [("period", "text"), ("created_at", "dt")],
        "unique": ["id"],
    },
    "documents": {
        "extract": [("code", "code"), ("title", "text"), ("kind", "text"),
                    ("status", "text"), ("current_version", "text"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "document_versions": {
        "extract": [("document_id", "text"), ("version", "text"), ("created_at", "dt")],
        "unique": ["id"],
    },
    "instruments": {
        "extract": [("code", "code"), ("name", "text"), ("interface", "text"),
                    ("agent_id", "text"), ("status", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "instrument_agents": {
        "extract": [("code", "code"), ("agent_token", "text"), ("status", "text"),
                    ("last_heartbeat", "dt"), ("created_at", "dt")],
        "unique": ["id", "code", "agent_token"],
    },
    "instrument_readings": {
        "extract": [("instrument_id", "text"), ("timestamp", "dt")],
        "unique": ["id"],
    },
    "system_modules": {
        "extract": [("key", "code"), ("enabled", "bool"), ("updated_at", "dt")],
        "unique": ["id", "key"],
    },
    "local_admin": {
        "extract": [("email", "text"), ("updated_at", "dt")],
        "unique": ["id"],
    },
    "hr_employees": {
        "extract": [("code", "code"), ("cedula", "text"), ("name", "text"),
                    ("position", "text"), ("department", "text"),
                    ("salary_base", "num"), ("status", "text"), ("created_at", "dt")],
        "unique": ["id", "code", "cedula"],
    },
    "hr_payroll_runs": {
        "extract": [("period", "code"), ("generated_at", "dt"), ("employee_count", "num")],
        "unique": ["id", "period"],
    },
    "ehs_accidents": {
        "extract": [("code", "code"), ("date", "text"), ("severity", "text"),
                    ("with_injury", "bool"), ("lost_days", "num"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "sales_clients": {
        "extract": [("code", "code"), ("name", "text"), ("tax_id", "text"),
                    ("active", "bool"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "sales_quotes": {
        "extract": [("code", "code"), ("client_id", "text"), ("status", "text"),
                    ("total", "num"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "sales_invoices": {
        "extract": [("code", "code"), ("client_id", "text"), ("status", "text"),
                    ("total", "num"), ("due_date", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "maintenance_wo": {
        "extract": [("code", "code"), ("equipment_id", "text"), ("type", "text"),
                    ("status", "text"), ("priority", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "logistics_carriers": {
        "extract": [("code", "code"), ("name", "text"), ("tax_id", "text"),
                    ("active", "bool"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "logistics_fleet": {
        "extract": [("code", "code"), ("plate", "text"), ("type", "text"),
                    ("status", "text"), ("carrier_id", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "logistics_routes": {
        "extract": [("code", "code"), ("name", "text"), ("origin", "text"),
                    ("destination", "text"), ("active", "bool"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "logistics_dispatches": {
        "extract": [("code", "code"), ("invoice_id", "text"), ("client_id", "text"),
                    ("carrier_id", "text"), ("vehicle_id", "text"), ("route_id", "text"),
                    ("status", "text"), ("scheduled_date", "text"),
                    ("delivered_at", "dt"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "rnd_projects": {
        "extract": [("code", "code"), ("name", "text"), ("stage", "text"),
                    ("status", "text"), ("owner_id", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "ehs_incidents": {
        "extract": [("code", "code"), ("date", "text"), ("severity", "text"),
                    ("area", "text"), ("status", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "ehs_ppe": {
        "extract": [("code", "code"), ("employee_id", "text"), ("ppe_type", "text"),
                    ("delivered_at", "text"), ("status", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "ehs_inspections": {
        "extract": [("code", "code"), ("date", "text"), ("area", "text"),
                    ("inspector", "text"), ("status", "text"), ("score", "num"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "inventory_counts": {
        "extract": [("code", "code"), ("warehouse_id", "text"), ("status", "text"),
                    ("counted_at", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    # ==== Iter 15 (Aug 2026) · Priority submodules from PDF ====
    "ap_invoices": {  # Cuentas por Pagar - facturas de proveedores
        "extract": [("code", "code"), ("supplier_id", "text"),
                    ("supplier_code", "text"), ("status", "text"),
                    ("total", "num"), ("balance", "num"), ("currency", "text"),
                    ("issue_date", "text"), ("due_date", "text"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "ap_payments": {  # Cuentas por Pagar - pagos a proveedores
        "extract": [("code", "code"), ("ap_invoice_id", "text"),
                    ("amount", "num"), ("method", "text"),
                    ("paid_at", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "ar_payments": {  # Cuentas por Cobrar - cobros de clientes
        "extract": [("code", "code"), ("invoice_id", "text"),
                    ("amount", "num"), ("method", "text"),
                    ("paid_at", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "sales_orders": {  # Órdenes de venta (draft→confirmada→despachada→facturada)
        "extract": [("code", "code"), ("client_id", "text"),
                    ("quote_id", "text"), ("invoice_id", "text"),
                    ("dispatch_id", "text"), ("status", "text"),
                    ("total", "num"), ("currency", "text"),
                    ("delivery_date", "text"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "inventory_transfers": {  # Transferencias entre almacenes
        "extract": [("code", "code"), ("from_warehouse_id", "text"),
                    ("to_warehouse_id", "text"), ("status", "text"),
                    ("requested_at", "text"), ("approved_at", "dt"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "recipes": {  # Recetas / Fórmulas de producción (BOM con versionado)
        "extract": [("code", "code"), ("product_id", "text"), ("version", "text"),
                    ("status", "text"), ("yield_qty", "num"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    # ==== Iter 16 (Aug 2026) · Inventory ext + HR ext ====
    "tanks": {  # Tanques / Silos con capacidad y volumen actual
        "extract": [("code", "code"), ("name", "text"), ("location", "text"),
                    ("tank_type", "text"), ("capacity_l", "num"),
                    ("current_volume_l", "num"), ("fill_pct", "num"),
                    ("active", "bool"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "batch_quarantines": {  # Bloqueo / Cuarentena de lotes
        "extract": [("code", "code"), ("batch_id", "text"),
                    ("batch_code", "text"), ("status", "text"),
                    ("created_at", "dt")],
        "unique": ["id", "code"],
    },
    "vacations": {  # Solicitudes de vacaciones y permisos
        "extract": [("code", "code"), ("employee_id", "text"),
                    ("type", "text"), ("status", "text"),
                    ("start_date", "text"), ("end_date", "text"),
                    ("days", "num"), ("created_at", "dt")],
        "unique": ["id", "code"],
    },
}


TABLES: Dict[str, Table] = {}


def _build_tables():
    for name, cfg in _COLLECTIONS.items():
        cols = [Column("_pk", Integer, primary_key=True, autoincrement=True),
                Column("id", _short(64), nullable=False, index=True)]
        # extract columns
        seen = {"id", "_pk"}
        for (col_name, kind) in cfg.get("extract", []):
            if col_name in seen: continue
            cols.append(_mkcol(col_name, kind, index=True))
            seen.add(col_name)
        cols.append(Column("data", _text(), nullable=False))

        constraints: List[Any] = []
        # Unique constraints
        for u in cfg.get("unique", []):
            if u == "id":
                constraints.append(UniqueConstraint("id", name=f"ux_{name}_id"))
            elif u in seen:
                constraints.append(UniqueConstraint(u, name=f"ux_{name}_{u}"))

        table_name = f"ylms_{name}"
        table = Table(table_name, metadata, *cols, *constraints, extend_existing=False)
        TABLES[name] = table


_build_tables()

# Track "custom id field" (e.g. counters._id, settings._id) so writes/reads translate.
CUSTOM_ID_FIELD = {name: cfg.get("id_field", "id") for name, cfg in _COLLECTIONS.items()}


# ------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------

async def init_database():
    """Create tables + dialect-specific extras (audit triggers, sprocs)."""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
        if _is_mssql:
            await _mssql_post_create(conn)


async def _mssql_post_create(conn):
    """Create audit trigger and stored procedures on MSSQL only."""
    # Example stored procedure: seq generator
    await conn.execute(text("""
    IF NOT EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_next_seq')
    EXEC ('
    CREATE PROCEDURE sp_next_seq @seq_name NVARCHAR(64), @out INT OUTPUT AS
    BEGIN
        DECLARE @data NVARCHAR(MAX);
        SELECT @data = data FROM ylms_counters WHERE _id_str = @seq_name;
        IF @data IS NULL
        BEGIN
            SET @out = 1;
            INSERT INTO ylms_counters (id, _id_str, data) VALUES (@seq_name, @seq_name, ''{"seq":1}'');
        END
        ELSE
        BEGIN
            SET @out = TRY_CONVERT(INT, JSON_VALUE(@data, ''$.seq'')) + 1;
            UPDATE ylms_counters SET data = JSON_MODIFY(data, ''$.seq'', @out) WHERE _id_str = @seq_name;
        END
    END
    ')
    """))
    # Audit trigger: replicate change events to audit_logs when INSERT/UPDATE/DELETE on
    # sensitive tables. We keep the app-level audit_util as the primary source and use
    # this trigger as a database-side redundancy.
    for src in ("ylms_users", "ylms_samples", "ylms_batches", "ylms_coa", "ylms_lab_form_records"):
        trg = f"trg_audit_{src}"
        await conn.execute(text(f"""
        IF NOT EXISTS (SELECT * FROM sys.triggers WHERE name = '{trg}')
        EXEC ('
        CREATE TRIGGER {trg} ON {src} AFTER INSERT, UPDATE, DELETE AS
        BEGIN
            SET NOCOUNT ON;
            DECLARE @op NVARCHAR(10) =
                CASE WHEN EXISTS(SELECT 1 FROM inserted) AND EXISTS(SELECT 1 FROM deleted) THEN ''update''
                     WHEN EXISTS(SELECT 1 FROM inserted) THEN ''insert''
                     ELSE ''delete'' END;
            INSERT INTO ylms_audit_logs (id, action, module, entity_id, timestamp, data)
            SELECT NEWID(), ''db_'' + @op, ''{src}'', COALESCE(i.id, d.id),
                   CONVERT(NVARCHAR(30), SYSDATETIMEOFFSET(), 127),
                   ''{{}}''
            FROM inserted i FULL OUTER JOIN deleted d ON i.id = d.id;
        END
        ')
        """))


# ------------------------------------------------------------------
# JSON serialization helpers
# ------------------------------------------------------------------

def _json_dumps(x: Any) -> str:
    return json.dumps(x, default=str, ensure_ascii=False)


def _json_loads(s: Any) -> Any:
    if s is None:
        return {}
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return {}


def _extract_values(name: str, doc: dict) -> Dict[str, Any]:
    """Return dict of the extract-columns for this doc (excluding data itself)."""
    cfg = _COLLECTIONS[name]
    id_field = cfg.get("id_field", "id")
    row: Dict[str, Any] = {}
    # id column: for counters/settings which use _id, store that value under `id`.
    if id_field == "id":
        row["id"] = str(doc.get("id") or uuid.uuid4())
    else:
        row["id"] = str(doc.get(id_field) or doc.get("id") or uuid.uuid4())
        # also copy the raw _id into extract col _id_str
        row["_id_str"] = str(doc.get(id_field) or doc.get("id"))
    for (col_name, kind) in cfg.get("extract", []):
        if col_name == "_id_str":
            continue
        v = doc.get(col_name)
        if kind == "num" and v is not None:
            try: v = float(v)
            except (TypeError, ValueError): v = None
        if kind == "int" and v is not None:
            try: v = int(v)
            except (TypeError, ValueError): v = None
        if kind == "bool" and v is not None:
            v = bool(v)
        row[col_name] = v
    return row


# ------------------------------------------------------------------
# Mongo-compatibility API
# ------------------------------------------------------------------

class Cursor:
    def __init__(self, coll: "Collection", query: dict, projection: Optional[dict] = None):
        self._coll = coll
        self._query = query or {}
        self._proj = projection
        self._sort: List[Tuple[str, int]] = []
        self._limit: Optional[int] = None
        self._skip: Optional[int] = None

    def sort(self, field, direction: int = 1):
        # Motor allows .sort("field", -1) or .sort([("field", -1)])
        if isinstance(field, str):
            self._sort.append((field, direction))
        elif isinstance(field, list):
            self._sort.extend(field)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    async def to_list(self, length: Optional[int] = None):
        if length is not None:
            self._limit = length if self._limit is None else min(self._limit, length)
        return await self._coll._execute_find(self._query, self._proj, self._sort,
                                               self._limit, self._skip)

    def __aiter__(self):
        return self._aiter()

    async def _aiter(self):
        items = await self.to_list(None)
        for it in items:
            yield it


def _apply_query(table: Table, query: dict):
    """Translate a subset of Mongo-style query into SQL where clauses.

    Supported operators: $eq, $ne, $in, $nin, $gt, $gte, $lt, $lte, $regex, $exists.
    Supported logical: $or (top-level).
    Non-extracted fields are applied as post-filter (Python side).
    """
    conds = []
    py_filters: Dict[str, Any] = {}
    col_names = {c.name for c in table.columns}
    for k, v in query.items():
        if k == "$or":
            sub_conds = []
            sub_py = []
            for sub in v:
                sc, sp = _apply_query(table, sub)
                sub_conds.append(and_(*sc)) if sc else None
                sub_py.append(sp)
            if sub_conds:
                conds.append(or_(*sub_conds))
            if any(sub_py):
                # We can't OR python side generally; fallback: skip py filters when using $or.
                pass
            continue
        if k not in col_names:
            py_filters[k] = v
            continue
        c = table.c[k]
        if isinstance(v, dict):
            for op, val in v.items():
                if op == "$eq": conds.append(c == val)
                elif op == "$ne": conds.append(c != val)
                elif op == "$in": conds.append(c.in_(list(val)))
                elif op == "$nin": conds.append(~c.in_(list(val)))
                elif op == "$gt": conds.append(c > val)
                elif op == "$gte": conds.append(c >= val)
                elif op == "$lt": conds.append(c < val)
                elif op == "$lte": conds.append(c <= val)
                elif op == "$exists":
                    conds.append(c.isnot(None) if val else c.is_(None))
                elif op == "$regex":
                    pattern = re.escape(val) if not isinstance(val, str) else val
                    like = "%" + val.replace("%", "\\%").replace("_", "\\_") + "%"
                    conds.append(c.ilike(like) if not _is_mssql else func.lower(c).like(like.lower()))
                else:
                    py_filters.setdefault(k, {})[op] = val
        else:
            conds.append(c == v)
    return conds, py_filters


def _post_filter(items: List[dict], py_filters: dict) -> List[dict]:
    if not py_filters:
        return items
    out = []
    for it in items:
        ok = True
        for k, v in py_filters.items():
            if isinstance(v, dict):
                for op, val in v.items():
                    xv = _dig(it, k)
                    if op == "$eq" and xv != val: ok = False; break
                    elif op == "$ne" and xv == val: ok = False; break
                    elif op == "$in" and xv not in val: ok = False; break
                    elif op == "$gt" and not (xv is not None and xv > val): ok = False; break
                    elif op == "$gte" and not (xv is not None and xv >= val): ok = False; break
                    elif op == "$lt" and not (xv is not None and xv < val): ok = False; break
                    elif op == "$lte" and not (xv is not None and xv <= val): ok = False; break
                    elif op == "$regex" and (xv is None or not re.search(val, str(xv), re.IGNORECASE)): ok = False; break
            else:
                if _dig(it, k) != v: ok = False; break
            if not ok: break
        if ok: out.append(it)
    return out


def _dig(d: dict, key: str):
    if "." in key:
        parts = key.split(".")
        v = d
        for p in parts:
            if isinstance(v, dict): v = v.get(p)
            else: return None
        return v
    return d.get(key)


class Collection:
    def __init__(self, name: str):
        self.name = name
        self.table = TABLES[name]

    async def create_index(self, *args, **kwargs):
        # no-op; indexes created via SQLAlchemy metadata
        return None

    async def create_indexes(self, *args, **kwargs):
        return None

    def aggregate(self, pipeline: List[dict]):
        """Minimal aggregation pipeline supporting:
        - $match           (uses _apply_query)
        - $project         (dict of key -> field ref '$field' or literal / $cond / $eq / $multiply / $add / $subtract / $sum)
        - $addFields       (same as $project but keeps other fields)
        - $group           (_id, $sum, $count, $last, $first, $max, $min, $avg, $push)
        - $sort            (dict of field -> 1/-1)
        - $limit / $skip

        Returns an AggregateCursor with .to_list().
        """
        return AggregateCursor(self, pipeline)

    # ---- writes ----
    async def insert_one(self, doc: dict):
        payload = dict(doc)
        payload.pop("_id", None)
        payload.pop("_pk", None)
        # ensure id
        id_field = CUSTOM_ID_FIELD[self.name]
        if id_field == "id" and not payload.get("id"):
            payload["id"] = str(uuid.uuid4())
        row = _extract_values(self.name, payload)
        row["data"] = _json_dumps(payload)
        async with async_session_factory() as sess:
            await sess.execute(insert(self.table).values(**row))
            await sess.commit()
        return type("R", (), {"inserted_id": row["id"]})

    async def insert_many(self, docs: List[dict]):
        async with async_session_factory() as sess:
            for d in docs:
                p = dict(d); p.pop("_id", None); p.pop("_pk", None)
                if CUSTOM_ID_FIELD[self.name] == "id" and not p.get("id"):
                    p["id"] = str(uuid.uuid4())
                row = _extract_values(self.name, p); row["data"] = _json_dumps(p)
                await sess.execute(insert(self.table).values(**row))
            await sess.commit()
        return type("R", (), {"inserted_ids": []})

    async def _find_row(self, query: dict, sess: AsyncSession):
        conds, py = _apply_query(self.table, query)
        stmt = select(self.table).where(and_(*conds)) if conds else select(self.table)
        result = await sess.execute(stmt)
        rows = result.mappings().all()
        docs = [self._row_to_doc(r) for r in rows]
        if py:
            # Keep rows and docs aligned when post-filtering.
            paired = [(r, d) for r, d in zip(rows, docs) if _post_filter([d], py)]
            rows = [r for r, _ in paired]
            docs = [d for _, d in paired]
        return rows, docs

    async def update_one(self, query: dict, update_ops: dict, upsert: bool = False):
        async with async_session_factory() as sess:
            rows, docs = await self._find_row(query, sess)
            if docs:
                current = docs[0]
                new_doc = _apply_update(current, update_ops)
                extracted = _extract_values(self.name, new_doc)
                extracted["data"] = _json_dumps(new_doc)
                pk = rows[0]["_pk"]
                await sess.execute(update(self.table).where(self.table.c._pk == pk).values(**extracted))
                await sess.commit()
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})
            if upsert:
                new_doc = {}
                _apply_update_inplace(new_doc, update_ops)
                # $setOnInsert equality clauses from query
                for k, v in query.items():
                    if isinstance(v, dict): continue
                    if k not in new_doc: new_doc[k] = v
                if CUSTOM_ID_FIELD[self.name] == "id" and not new_doc.get("id"):
                    new_doc["id"] = str(uuid.uuid4())
                extracted = _extract_values(self.name, new_doc)
                extracted["data"] = _json_dumps(new_doc)
                await sess.execute(insert(self.table).values(**extracted))
                await sess.commit()
                return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": new_doc.get("id")})
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})

    async def update_many(self, query: dict, update_ops: dict):
        async with async_session_factory() as sess:
            rows, docs = await self._find_row(query, sess)
            n = 0
            for r, current in zip(rows, docs):
                new_doc = _apply_update(current, update_ops)
                ext = _extract_values(self.name, new_doc); ext["data"] = _json_dumps(new_doc)
                await sess.execute(update(self.table).where(self.table.c._pk == r["_pk"]).values(**ext))
                n += 1
            await sess.commit()
            return type("R", (), {"matched_count": n, "modified_count": n})

    async def replace_one(self, query: dict, new_doc: dict, upsert: bool = False):
        async with async_session_factory() as sess:
            rows, docs = await self._find_row(query, sess)
            if docs:
                merged = dict(new_doc)
                merged.pop("_pk", None)
                # Ensure custom-id field survives even if caller didn't include it
                id_field = CUSTOM_ID_FIELD[self.name]
                if id_field != "id" and not merged.get(id_field) and query.get(id_field):
                    merged[id_field] = query[id_field]
                ext = _extract_values(self.name, merged); ext["data"] = _json_dumps(merged)
                await sess.execute(update(self.table).where(self.table.c._pk == rows[0]["_pk"]).values(**ext))
                await sess.commit()
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})
            if upsert:
                merged = dict(new_doc); merged.pop("_pk", None)
                id_field = CUSTOM_ID_FIELD[self.name]
                if id_field == "id" and not merged.get("id"):
                    merged["id"] = str(uuid.uuid4())
                if id_field != "id" and not merged.get(id_field) and query.get(id_field):
                    merged[id_field] = query[id_field]
                ext = _extract_values(self.name, merged); ext["data"] = _json_dumps(merged)
                await sess.execute(insert(self.table).values(**ext))
                await sess.commit()
                return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": merged.get("id")})
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})

    async def delete_one(self, query: dict):
        async with async_session_factory() as sess:
            rows, docs = await self._find_row(query, sess)
            if not rows:
                return type("R", (), {"deleted_count": 0})
            await sess.execute(delete(self.table).where(self.table.c._pk == rows[0]["_pk"]))
            await sess.commit()
            return type("R", (), {"deleted_count": 1})

    async def delete_many(self, query: dict):
        async with async_session_factory() as sess:
            rows, docs = await self._find_row(query, sess)
            for r in rows:
                await sess.execute(delete(self.table).where(self.table.c._pk == r["_pk"]))
            await sess.commit()
            return type("R", (), {"deleted_count": len(rows)})

    async def find_one(self, query: dict, projection: Optional[dict] = None):
        async with async_session_factory() as sess:
            _, docs = await self._find_row(query, sess)
        if not docs:
            return None
        return _apply_projection(docs[0], projection)

    def find(self, query: dict = None, projection: Optional[dict] = None):
        return Cursor(self, query or {}, projection)

    async def _execute_find(self, query, projection, sort, limit, skip):
        conds, py = _apply_query(self.table, query)
        stmt = select(self.table)
        if conds:
            stmt = stmt.where(and_(*conds))
        col_names = {c.name for c in self.table.columns}
        for (field, direction) in sort:
            if field in col_names:
                col = self.table.c[field]
                stmt = stmt.order_by(col.desc() if direction < 0 else col.asc())
        if limit and not py:
            stmt = stmt.limit(limit)
            if skip: stmt = stmt.offset(skip)
        async with async_session_factory() as sess:
            result = await sess.execute(stmt)
            rows = result.mappings().all()
        docs = [self._row_to_doc(r) for r in rows]
        if py:
            docs = _post_filter(docs, py)
        # Sort by non-extracted fields
        non_col_sort = [(f, d) for (f, d) in sort if f not in col_names]
        for (f, d) in reversed(non_col_sort):
            docs.sort(key=lambda x: (x.get(f) is None, x.get(f)), reverse=(d < 0))
        if py:
            if skip: docs = docs[skip:]
            if limit: docs = docs[:limit]
        return [_apply_projection(x, projection) for x in docs]

    async def count_documents(self, query: dict):
        conds, py = _apply_query(self.table, query or {})
        async with async_session_factory() as sess:
            if not py:
                stmt = select(func.count()).select_from(self.table)
                if conds: stmt = stmt.where(and_(*conds))
                r = await sess.execute(stmt)
                return int(r.scalar() or 0)
            else:
                _, docs = await self._find_row(query or {}, sess)
                return len(docs)

    async def find_one_and_update(self, query: dict, update_ops: dict,
                                    upsert: bool = False, return_document: bool = False):
        async with async_session_factory() as sess:
            rows, docs = await self._find_row(query, sess)
            if docs:
                current = docs[0]; pk = rows[0]["_pk"]
                new_doc = _apply_update(current, update_ops)
                ext = _extract_values(self.name, new_doc); ext["data"] = _json_dumps(new_doc)
                await sess.execute(update(self.table).where(self.table.c._pk == pk).values(**ext))
                await sess.commit()
                return new_doc if return_document else current
            if upsert:
                new_doc = {}
                _apply_update_inplace(new_doc, update_ops)
                for k, v in query.items():
                    if isinstance(v, dict): continue
                    if k not in new_doc: new_doc[k] = v
                id_field = CUSTOM_ID_FIELD[self.name]
                if id_field != "id" and id_field in query and not new_doc.get(id_field):
                    new_doc[id_field] = query[id_field]
                if id_field == "id" and not new_doc.get("id"):
                    new_doc["id"] = str(uuid.uuid4())
                ext = _extract_values(self.name, new_doc); ext["data"] = _json_dumps(new_doc)
                await sess.execute(insert(self.table).values(**ext))
                await sess.commit()
                return new_doc if return_document else None
            return None

    def _row_to_doc(self, row) -> dict:
        base = _json_loads(row["data"])
        # ensure id in the doc
        id_field = CUSTOM_ID_FIELD[self.name]
        if id_field != "id":
            base[id_field] = row["_id_str"] if row.get("_id_str") is not None else base.get(id_field)
        else:
            base["id"] = row["id"]
        return base


def _apply_projection(doc: dict, projection: Optional[dict]) -> dict:
    if not projection or not isinstance(doc, dict):
        return doc
    exclude = [k for k, v in projection.items() if v == 0]
    include = [k for k, v in projection.items() if v == 1]
    d = dict(doc)
    if exclude:
        for e in exclude:
            d.pop(e, None)
    if include:
        d = {k: v for k, v in d.items() if k in include or k in ("id", "_id")}
    return d


def _apply_update(current: dict, update_ops: dict) -> dict:
    out = dict(current)
    _apply_update_inplace(out, update_ops)
    return out


def _apply_update_inplace(doc: dict, update_ops: dict):
    if not any(k.startswith("$") for k in update_ops.keys()):
        doc.update(update_ops)
        return
    for op, payload in update_ops.items():
        if op == "$set":
            for k, v in payload.items():
                _set_dotted(doc, k, v)
        elif op == "$unset":
            for k in payload.keys():
                _unset_dotted(doc, k)
        elif op == "$inc":
            for k, v in payload.items():
                cur = _get_dotted(doc, k) or 0
                _set_dotted(doc, k, (cur or 0) + v)
        elif op == "$push":
            for k, v in payload.items():
                arr = _get_dotted(doc, k) or []
                if not isinstance(arr, list): arr = []
                arr.append(v); _set_dotted(doc, k, arr)
        elif op == "$pull":
            for k, v in payload.items():
                arr = _get_dotted(doc, k) or []
                if isinstance(arr, list):
                    arr = [x for x in arr if x != v]
                _set_dotted(doc, k, arr)
        elif op == "$addToSet":
            for k, v in payload.items():
                arr = _get_dotted(doc, k) or []
                if not isinstance(arr, list): arr = []
                if v not in arr: arr.append(v)
                _set_dotted(doc, k, arr)
        elif op == "$setOnInsert":
            # only applied on insert - handled by upsert logic
            pass
        else:
            # unsupported operator; ignore silently
            pass


def _set_dotted(d, key, val):
    if "." in key:
        parts = key.split("."); cur = d
        for p in parts[:-1]:
            cur.setdefault(p, {})
            cur = cur[p]
        cur[parts[-1]] = val
    else:
        d[key] = val


def _get_dotted(d, key):
    if "." in key:
        parts = key.split("."); cur = d
        for p in parts:
            if isinstance(cur, dict): cur = cur.get(p)
            else: return None
        return cur
    return d.get(key)


def _unset_dotted(d, key):
    if "." in key:
        parts = key.split("."); cur = d
        for p in parts[:-1]:
            if isinstance(cur, dict): cur = cur.get(p, {})
            else: return
        if isinstance(cur, dict): cur.pop(parts[-1], None)
    else:
        d.pop(key, None)


class Database:
    def __getattr__(self, item: str) -> Collection:
        if item not in TABLES:
            # Auto-create a collection with generic schema? we only support declared ones.
            raise AttributeError(f"Unknown collection: {item}")
        return Collection(item)

    def __getitem__(self, item: str) -> Collection:
        return getattr(self, item)


# ------------------------------------------------------------------
# Aggregation pipeline (minimal, in-memory implementation)
# ------------------------------------------------------------------

def _eval_expr(expr, doc: dict):
    """Evaluate an aggregation expression against a document."""
    if isinstance(expr, str):
        if expr.startswith("$"):
            return _dig(doc, expr[1:])
        return expr
    if isinstance(expr, (int, float, bool)) or expr is None:
        return expr
    if isinstance(expr, list):
        return [_eval_expr(x, doc) for x in expr]
    if isinstance(expr, dict):
        # Operators
        if "$cond" in expr:
            args = expr["$cond"]
            if isinstance(args, list):
                cond, t, f = args[0], args[1], args[2]
            else:
                cond, t, f = args["if"], args["then"], args["else"]
            return _eval_expr(t, doc) if _eval_expr(cond, doc) else _eval_expr(f, doc)
        if "$eq" in expr:
            a, b = expr["$eq"]
            return _eval_expr(a, doc) == _eval_expr(b, doc)
        if "$ne" in expr:
            a, b = expr["$ne"]
            return _eval_expr(a, doc) != _eval_expr(b, doc)
        if "$gt" in expr:
            a, b = expr["$gt"]; return _eval_expr(a, doc) > _eval_expr(b, doc)
        if "$gte" in expr:
            a, b = expr["$gte"]; return _eval_expr(a, doc) >= _eval_expr(b, doc)
        if "$lt" in expr:
            a, b = expr["$lt"]; return _eval_expr(a, doc) < _eval_expr(b, doc)
        if "$lte" in expr:
            a, b = expr["$lte"]; return _eval_expr(a, doc) <= _eval_expr(b, doc)
        if "$multiply" in expr:
            vals = [_eval_expr(x, doc) or 0 for x in expr["$multiply"]]
            r = 1
            for v in vals: r *= v
            return r
        if "$add" in expr:
            return sum((_eval_expr(x, doc) or 0) for x in expr["$add"])
        if "$subtract" in expr:
            a, b = expr["$subtract"]
            return (_eval_expr(a, doc) or 0) - (_eval_expr(b, doc) or 0)
        if "$divide" in expr:
            a, b = expr["$divide"]
            bv = _eval_expr(b, doc); return (_eval_expr(a, doc) or 0) / bv if bv else 0
        if "$sum" in expr:
            v = expr["$sum"]
            if isinstance(v, (int, float)):
                return v
            return _eval_expr(v, doc) or 0
        if "$toDouble" in expr:
            try: return float(_eval_expr(expr["$toDouble"], doc) or 0)
            except (TypeError, ValueError): return 0.0
        if "$ifNull" in expr:
            a, b = expr["$ifNull"]
            v = _eval_expr(a, doc)
            return v if v is not None else _eval_expr(b, doc)
        # else treat as literal dict
        return {k: _eval_expr(v, doc) for k, v in expr.items()}
    return expr


def _make_key(spec, doc):
    """Materialise a $group._id spec into a hashable key + kept dict."""
    if spec is None:
        return "__all__", None
    if isinstance(spec, str):
        return _eval_expr(spec, doc), _eval_expr(spec, doc)
    if isinstance(spec, dict):
        out = {}
        for k, v in spec.items():
            out[k] = _eval_expr(v, doc)
        return json.dumps(out, default=str, sort_keys=True), out
    return json.dumps(spec, default=str), spec


class AggregateCursor:
    def __init__(self, coll: "Collection", pipeline: List[dict]):
        self._coll = coll
        self._pipeline = pipeline
        self._limit: Optional[int] = None

    def limit(self, n: int):
        self._limit = n
        return self

    async def to_list(self, length: Optional[int] = None):
        # Load all docs from collection (best-effort; for aggregations we materialize)
        async with async_session_factory() as sess:
            result = await sess.execute(select(self._coll.table))
            rows = result.mappings().all()
        docs = [self._coll._row_to_doc(r) for r in rows]

        for stage in self._pipeline:
            (op, arg), = stage.items()
            if op == "$match":
                conds, py = _apply_query(self._coll.table, arg)
                # Since docs are already materialised, apply the whole query in Python.
                merged: Dict[str, Any] = {}
                for k, v in arg.items():
                    merged[k] = v
                docs = _post_filter(docs, merged)
            elif op == "$project":
                docs = [{k: _eval_expr(v, d) if not (v == 1 or v is True) else d.get(k)
                          for k, v in arg.items()} for d in docs]
            elif op == "$addFields":
                for d in docs:
                    for k, v in arg.items():
                        d[k] = _eval_expr(v, d)
            elif op == "$group":
                gid_spec = arg.get("_id")
                acc_specs = {k: v for k, v in arg.items() if k != "_id"}
                groups: Dict[str, dict] = {}
                for d in docs:
                    gk, gv = _make_key(gid_spec, d)
                    g = groups.get(gk)
                    if not g:
                        g = {"_id": gv, "_docs": []}
                        for ak in acc_specs.keys():
                            g[ak] = None
                        groups[gk] = g
                    g["_docs"].append(d)
                # accumulate
                new_docs = []
                for gk, g in groups.items():
                    result_doc = {"_id": g["_id"]}
                    for ak, aspec in acc_specs.items():
                        # aspec is like {"$sum": expr} or {"$count": {}} etc.
                        (aop, aval), = aspec.items() if isinstance(aspec, dict) else [(None, None)]
                        vals = [_eval_expr(aval, d) for d in g["_docs"]] if aop else []
                        if aop == "$sum":
                            if isinstance(aval, (int, float)):
                                result_doc[ak] = len(g["_docs"]) * aval
                            else:
                                result_doc[ak] = sum((v or 0) for v in vals)
                        elif aop == "$count":
                            result_doc[ak] = len(g["_docs"])
                        elif aop == "$last":
                            result_doc[ak] = vals[-1] if vals else None
                        elif aop == "$first":
                            result_doc[ak] = vals[0] if vals else None
                        elif aop == "$max":
                            non_none = [v for v in vals if v is not None]
                            result_doc[ak] = max(non_none) if non_none else None
                        elif aop == "$min":
                            non_none = [v for v in vals if v is not None]
                            result_doc[ak] = min(non_none) if non_none else None
                        elif aop == "$avg":
                            non_none = [v for v in vals if v is not None]
                            result_doc[ak] = sum(non_none) / len(non_none) if non_none else 0
                        elif aop == "$push":
                            result_doc[ak] = vals
                        elif aop == "$addToSet":
                            seen = []
                            for v in vals:
                                if v not in seen: seen.append(v)
                            result_doc[ak] = seen
                        else:
                            result_doc[ak] = None
                    new_docs.append(result_doc)
                docs = new_docs
            elif op == "$sort":
                for field, direction in reversed(list(arg.items())):
                    docs.sort(key=lambda x: (_dig(x, field) is None, _dig(x, field)),
                              reverse=(direction < 0))
            elif op == "$limit":
                docs = docs[:arg]
            elif op == "$skip":
                docs = docs[arg:]
            elif op == "$unwind":
                field = arg if isinstance(arg, str) else arg.get("path")
                if field.startswith("$"): field = field[1:]
                unwound = []
                for d in docs:
                    arr = _dig(d, field) or []
                    if not isinstance(arr, list): arr = [arr]
                    for item in arr:
                        nd = dict(d); _set_dotted(nd, field, item)
                        unwound.append(nd)
                docs = unwound
            else:
                # ignore unsupported stage
                pass

        if length is not None:
            docs = docs[:length]
        elif self._limit:
            docs = docs[:self._limit]
        return docs


_db = Database()


def get_db() -> Database:
    return _db


async def close_client():
    await engine.dispose()
