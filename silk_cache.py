"""ذاكرة تخزين مؤقت للطلبات — tiny on-disk JSON cache for GET responses.

Pure-stdlib import (json+hashlib+os). `requests` is imported lazily inside
cached_get so `import silk_cache` works offline / without the library.
Founding principle: on any network error return None — never crash, never
fabricate. Cache files live under data/cache/ (gitignored).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from urllib.parse import urlencode

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.join("data", "cache")
_TIMEOUT = 30
_TIMEOUT_PAIR = (10, _TIMEOUT)          # EXT-11: اتصالٌ ≤ ١٠ ث، قراءةٌ كما كانت
# EXT-2: علامةُ «الجلبُ الحيّ جرى وفشل» — تُعاد بدل `None` حين يطلبها المستدعي
# (`fail_sentinel=`)، فيميّز فشلَ المصدر عن تعطّل طبقة الكاش ولا يجلب حيّاً مرّتين.
_FETCH_FAILED = object()


def _cache_dir() -> str:
    """مجلد التخزين وقت النداء — resolve at call time (env or default).

    `SILK_CACHE_DIR` يوجّه الملفات لقرص دائم في النشر (Railway volume على
    /data/cache مثلًا) فتنجو ذاكرة الطلبات من إعادة النشر؛ يليه اشتقاق من
    `SILK_DATA_DIR` (متغير واحد يوجّه كل المخازن)، ثم الافتراضي المحلي.
    Env override so the request cache survives redeploys on a mounted volume.
    """
    explicit = os.environ.get("SILK_CACHE_DIR", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("SILK_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "cache")
    return _CACHE_DIR


def _count(kind: str) -> None:
    """سجّل حدثاً في عدّاد اقتصاد البيانات — best-effort, never breaks a fetch."""
    try:
        import silk_context  # lazy: keep this module's pure-stdlib import
        silk_context.count_data(kind)
    except Exception:  # noqa: BLE001 — العدّ شفافية لا شرط
        pass


def _key(url: str, params: dict | None) -> str:
    """مفتاح التخزين — sha1 of url + sorted params."""
    raw = url + "?" + urlencode(sorted((params or {}).items()))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cached_get(
    url: str, params: dict | None = None, ttl_seconds: int = 86400,
    fetcher=None, headers: dict | None = None, *,
    fail_sentinel=None, cacheable=None, short_lived=None,
    empty_ttl_seconds: int = 600,
) -> dict | list | None:
    """جلب مع تخزين مؤقت — GET JSON, serving fresh cache or fetching live.

    Returns parsed JSON (dict|list), or None on any network/parse error.
    `fetcher(url, params)` يُحقن من طبقة البيانات لاستعمال الجلسة المجمّعة
    (keep-alive)؛ بدونه يسقط إلى requests.get (تشغيل مستقل). Injected pooled
    getter for connection reuse; falls back to requests.get standalone.

    `headers` (اختياري): ترويسات طلب — لمصادر تمرّر مفتاحاً في ترويسة لا في
    الاستعلام (WTO: `Ocp-Apim-Subscription-Key`)، فلا يظهر السرّ في الـURL.
    **لا تدخل مفتاح التخزين** (مفتاح ثابت للخادم؛ إدراجه يمنع أي إصابة كاش
    ويعيد السرّ للتجزئة بلا داعٍ) — نفس منطق الاستعلام أحادي المستأجر.

    EXT (تدقيق 2026-09-01): `fail_sentinel` يُعاد بدل `None` حين يجري الجلبُ الحيّ
    ويفشل (EXT-2)؛ `cacheable(payload)` False ⇒ لا يُكتَب (أغلفةُ الخطأ، EXT-3)؛
    `short_lived(payload)` True ⇒ يُكتَب بطابعٍ مؤخَّر فينقضي بعد `empty_ttl_seconds`
    (الردودُ الفارغة)؛ والكتابةُ ذرّية (`.tmp` ثم `os.replace`، EXT-4)."""
    cache_dir = _cache_dir()
    path = os.path.join(cache_dir, _key(url, params) + ".json")
    try:  # سباق exists/getmtime — ملف يُحذف بينهما لا يُسقط الطلب
        fresh = (time.time() - os.path.getmtime(path)) < ttl_seconds
    except OSError:
        fresh = False
    if fresh:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            _count("cache_hits")
            return data
        except (OSError, ValueError) as exc:  # corrupt cache → refetch
            log.warning("cache read failed (%s); refetching", exc)

    try:
        import requests  # lazy: keep module importable offline
    except ImportError:
        log.warning("requests not installed — cannot fetch %s", url)
        return None

    _count("live_fetches")  # محاولة حية — تُحسب ولو فشلت (كلفة نداء فعلية)
    try:
        # headers شرطيّ: بلا ترويسات يبقى النداء مطابقاً حرفياً للتوقيع القديم
        # (لا يكسر مستدعياً/محاكاةً قائمةً بتوقيع الوسيطين) — الترويسات مسار
        # WTO الجديد وحده.
        if fetcher is not None:
            resp = (fetcher(url, params, headers=headers)
                    if headers is not None else fetcher(url, params))
        elif headers is not None:
            resp = requests.get(url, params=params, headers=headers,
                                timeout=_TIMEOUT_PAIR)
        else:
            resp = requests.get(url, params=params, timeout=_TIMEOUT_PAIR)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network/HTTP/JSON — never crash, never fabricate
        # R7 (API-10): نصُّ `HTTPError` يحمل الرابطَ بمعامله — يُنقَّح قبل السجلّ.
        try:
            from silk_diagnostics import _redact
            _msg = _redact(str(exc))
        except Exception:  # noqa: BLE001
            _msg = type(exc).__name__
        log.warning("cached_get failed for %s: %s", url, _msg)
        return fail_sentinel
    try:
        if cacheable is not None and not cacheable(data):
            return data                      # EXT-3: غلافُ خطأٍ — لا يُخزَّن
    except Exception:  # noqa: BLE001 — مسندٌ معطوب لا يمنع الردّ
        return data
    try:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"       # EXT-4: كتابةٌ ذرّية — لا ملفَ مبتور
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
        try:
            if short_lived is not None and short_lived(data):
                # EXT-3: الفارغُ يعيش `empty_ttl_seconds` لا العمرَ كاملاً
                back = max(0, int(ttl_seconds) - int(empty_ttl_seconds))
                stamp = time.time() - back
                os.utime(path, (stamp, stamp))
        except Exception:  # noqa: BLE001
            pass
    except OSError as exc:  # caching is best-effort
        log.warning("cache write failed (%s)", exc)
    return data
