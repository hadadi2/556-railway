"""هوية الطلب والاستئناف — durable, principal-scoped research admission."""
import contextvars
import hashlib
import json
import unicodedata
from dataclasses import asdict, is_dataclass
from contextlib import contextmanager

_active = contextvars.ContextVar("research_request_identity", default=None)


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"),
                                     default=lambda value: asdict(value) if is_dataclass(value) else str(value)).encode()).hexdigest()


def resume_mismatches(incoming, stored):
    """الحقول المحذوفة ترث؛ تغيير هوية البحث يحتاج تشغيلة جديدة."""
    fields = ("product", "hs_code", "product_card", "own_price", "production_cost_per_unit", "agent_prefs")
    def canonical(value):
        return " ".join(unicodedata.normalize("NFKC", value).split()).casefold() if isinstance(value, str) else value
    mismatches = []
    for key in fields:
        value = incoming.get(key)
        if value is None:
            continue
        previous = stored.get(key)
        if key == "product_card" and isinstance(value, dict) and isinstance(previous, dict):
            value = dict(value)
            if incoming.get("production_cost_per_unit") is not None:
                value["cost_per_unit"] = incoming["production_cost_per_unit"]
            # own_price يضاف إلى البطاقة المحفوظة؛ ليس تغييراً في هوية مدخلها.
            previous = {k: previous.get(k) for k in value}
        if canonical(value) != canonical(previous):
            mismatches.append(key)
    return mismatches


def claim(key, principal, payload):
    import silk_storage as storage
    identity = fingerprint(["POST /research", principal, key])
    digest = fingerprint(payload)
    storage.init_db()
    with storage._open(storage._db_path()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS research_request_keys (identity TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, analysis_id INTEGER REFERENCES analyses(id), response_json TEXT, status_code INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM research_request_keys WHERE identity=?", (identity,)).fetchone()
        if old:
            return identity, dict(old), old["fingerprint"] != digest
        conn.execute("INSERT INTO research_request_keys(identity, fingerprint) VALUES (?,?)", (identity, digest))
    return identity, None, False


@contextmanager
def bind(identity):
    token = _active.set(identity)
    try:
        yield
    finally:
        _active.reset(token)


def allocated(conn, analysis_id):
    """نفس معاملة إنشاء التحليل: لا نافذة سقوط بين التخصيص وربط المفتاح."""
    identity = _active.get()
    if identity:
        changed = conn.execute("UPDATE research_request_keys SET analysis_id=? WHERE identity=? AND analysis_id IS NULL", (analysis_id, identity)).rowcount
        if changed != 1:
            raise RuntimeError("research idempotency allocation fence failed")


def finish(identity, body, status):
    import silk_storage as storage
    with storage._open(storage._db_path()) as conn:
        conn.execute("UPDATE research_request_keys SET response_json=?, status_code=? WHERE identity=?", (json.dumps(body, ensure_ascii=False, default=str), status, identity))


def release_unallocated(identity):
    """رفض مؤقت قبل التخصيص يُعاد؛ صف مرتبط بدراسة لا يُحرر أبداً."""
    import silk_storage as storage
    with storage._open(storage._db_path()) as conn:
        return conn.execute(
            "DELETE FROM research_request_keys WHERE identity=? AND analysis_id IS NULL AND response_json IS NULL",
            (identity,)).rowcount == 1
