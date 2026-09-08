"""تخزين ملفات المنصّة على القرص — on-disk file storage for uploaded images (PR-8).

قرص محلي فقط، لا خدمة سحابية — نفس سبب SQLite في هذا المشروع: خدمة واحدة،
وحدة تخزين Railway واحدة تُركَّب عليها. المسار يُشتقّ من `SILK_DATA_DIR`
الموحّد (كل بقية المخازن) ما لم يُضبَط `SILK_PLATFORM_STORAGE_DIR` صراحةً —
نفس نمط `db.db_path()`.

القائمة البيضاء للامتدادات مقصودة: `POST /platform/images` كان يقبل سابقاً
`ext` من العميل بلا تحقّق (حقل نصّي حرّ)، فامتدادٌ عشوائي كان يُصبح جزءاً من
مسار على القرص. الآن الامتداد نفسه — لا فقط اسم الملف الظاهر — يُقيَّد بقائمة
صور معروفة، فلا يبني استدعاءٌ لاحق مساراً بامتداد لم تُرِده هذه الوحدة.
"""
from __future__ import annotations

import os

_DEFAULT_DIR = "data/platform_files"

_MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}


def storage_dir() -> str:
    """جذر تخزين الملفات — resolved at call time (env or default)."""
    explicit = os.environ.get("SILK_PLATFORM_STORAGE_DIR", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("SILK_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "platform_files")
    return _DEFAULT_DIR


def validate_extension(ext: str) -> str:
    """طبّع الامتداد وتحقّق من القائمة البيضاء — lowercase, validated, or raise.

    `ValueError` لا اقتطاع صامت — امتدادٌ غير معروف عيب عميل (422)، لا اختيارٌ
    للنظام يقرّره بصمت. Unknown extension is a 422 client fault, never a
    silent coercion.
    """
    e = (ext or "").lstrip(".").lower()
    if e not in _MIME_BY_EXT:
        raise ValueError(
            f"unsupported image extension {ext!r}; allowed: "
            + ", ".join(sorted(_MIME_BY_EXT)))
    return e


def mime_for_extension(ext: str) -> str:
    return _MIME_BY_EXT[ext]


_MAGIC = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"),
          (b"GIF87a", "gif"), (b"GIF89a", "gif"))


def sniff_image_kind(head: bytes) -> str | None:
    """نوعُ الصورة من بايتاتها الأولى — R7 (AUTH-17/BIZ-9): `png`/`jpg`/`gif`/`webp`
    أو None لما ليس صورةً معروفة. Magic-byte sniff; None = not a known image."""
    head = bytes(head or b"")
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def extension_matches_kind(ext: str, kind: str) -> bool:
    """هل يطابق الامتدادُ المعلَن النوعَ المكتشَف؟ (`jpeg` ≡ `jpg`)."""
    return {"jpeg": "jpg"}.get((ext or "").lower(), (ext or "").lower()) == kind


def max_bytes() -> int:
    """أقصى حجم رفع مقبول — env-tunable; empty/invalid ⇒ الافتراضي المُعلَن."""
    raw = os.environ.get("SILK_PLATFORM_MAX_IMAGE_BYTES", "").strip()
    try:
        return int(raw) if raw else 10 * 1024 * 1024   # افتراضي ١٠ ميجابايت
    except ValueError:
        return 10 * 1024 * 1024


def write(storage_key: str, content: bytes) -> None:
    """اكتب الملف على القرص — storage_key مولَّد من الخادم دوماً، لا من العميل."""
    path = os.path.join(storage_dir(), storage_key)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def delete(storage_key: str) -> bool:
    """احذف ملفاً بمفتاحه — True إن أُزيل. غيابُه ليس عطلاً (صفٌّ بلا ملف يُحذَف)."""
    try:
        os.remove(path_for(storage_key))
        return True
    except FileNotFoundError:
        return False


def path_for(storage_key: str) -> str:
    return os.path.join(storage_dir(), storage_key)


def exists(storage_key: str) -> bool:
    return os.path.isfile(path_for(storage_key))
