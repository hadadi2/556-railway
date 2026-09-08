#!/usr/bin/env python3
"""رُتبة ٢ — خادم حقيقي بشكل الإنتاج (rung 2: the real-server harness).

> **القاعدة الجديدة (تأكيد المالك آخِراً لا أوّلاً).** قبل أن يُوسَم أيّ PR
> يمسّ سلوكاً إنتاجياً «جاهزاً»، نستنفد كل رُتب الاختبار. الرُتبة ٢: أقلِع
> **التطبيق الفعلي** بـuvicorn على ملف SQLite حقيقي مبذور بالمدوّنة القانونية
> الحقيقية الشكل (تمور × هولندا)، واضرب كل نقطة نهاية بـHTTP حقيقي. لا نموذج،
> لا TestClient — عملية خادم فعلية على منفذ فعلي.
>
> **What this is.** Boots the ACTUAL app (uvicorn) against a REAL SQLite file
> seeded with the canonical real-shape Netherlands blob, so rung-2 tests and
> the rung-3 Playwright flow both drive a real server over real HTTP.

المفاتيح المدفوعة (Claude/Comtrade) غائبة عمداً — نقاط القراءة/التصدير التي
تخدمها هذه البيئة (‏`/analyses`, `/analyses/{id}`, `report.md`, `report.docx`,
‏`/research/{id}/status`) تُقرَأ من المخزن ولا تلمس أيّ API خارجي، فلا حاجة
لأيّ محاكاة هنا؛ الطبقة الوحيدة التي كانت ستُحاكى (المزودون المدفوعون) لا
تُستدعى أصلاً على مسار الإسناد. أي تغيير قرب مسار المال يُشغّل رُتبة ٤
(‏tools/acceptance_run.py) بمزودين محاكَين بدلاً منها.

الاستعمال المستقل (standalone):
    python3 tools/live_shape_server.py --port 8099 --hold   # يبقى معلّقاً للتصفّح اليدوي
    python3 tools/live_shape_server.py --port 8099          # يُقلِع، يفحص /health، يطبع، يُغلق

الاستعمال المستورَد (اختبارات رُتبة ٢/٣):
    from live_shape_server import LiveShapeServer
    with LiveShapeServer() as srv:
        print(srv.base_url, srv.completed_id, srv.running_id)

المكتبات: stdlib فقط (subprocess/urllib/tempfile) — لا تبعيات جديدة.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

from canonical_netherlands import netherlands_research_blob  # noqa: E402


# R8 (TEST-1ب): صمّاماتٌ تُطفَأ في `tests/conftest.py` للسرعة — لا ترثها عمليةُ الخادم.
_SESSION_SWITCHES = ("SILK_PLATFORM_ORPHAN_SWEEP", "SILK_PLATFORM_RUN_SUPERVISOR",
                     "SILK_RATE_LIMIT", "SILK_EARLY_HALT")


def _free_port() -> int:
    """منفذ حرّ يمنحه النظام — يتجنّب تصادم المنافذ الثابتة في CI المتوازي."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def seed_db(db_path: str) -> tuple[int, int]:
    """ابذر ملف SQLite بالمدوّنة القانونية: صفّ مكتمل (تقرير كامل + تصدير)
    وصفّ جارٍ (شارة تقدّم «جارٍ التشغيل…» + زرّ استئناف في الشريط الجانبي).
    يعيد (completed_id, running_id). Seed a real DB; return the two row ids.

    نبذر عبر واجهات silk_storage الحقيقية نفسها التي يستعملها الإنتاج
    (`save_analysis` / `create_research_run`) — لا كتابة SQL يدوية تلتفّ على
    المخطّط الفعلي."""
    import silk_storage
    silk_storage.init_db(db_path)
    completed_id = silk_storage.save_analysis(
        netherlands_research_blob(), path=db_path)
    # صفّ جارٍ — يُظهر مسار التقدّم الحيّ في الشريط الجانبي (شارة + استئناف)
    # دون تشغيلة فعلية (deterministic، بلا نداء مدفوع).
    running_id = silk_storage.create_research_run(
        product="تمور", market_iso3="ESP", hs_code="080410",
        request_snapshot={"product": "تمور", "market": "ESP",
                          "hs_code": "080410"},
        path=db_path, market_name="إسبانيا")
    return completed_id, running_id


def seed_producer_export_cache(cache_dir: str, hs_code: str, year: int,
                               top_isos: list[tuple[str, str]]) -> None:
    """ابذر مخبأ كومتريد لتصدير العالم (flow=X) عبر المسار الحقيقي — no test-hook.

    يكتب ملف المخبأ بنفس مفتاح (url+params) الذي يبنيه `comtrade_trade(hs, None,
    year, flow="X", partner=0)` بلا مفتاح اشتراك (البيئة الحقيقية هنا تنزع
    COMTRADE_API_KEY)، فيقرؤه الخادم الحيّ **من المخبأ** بلا شبكة — فتُطلق
    استشارةُ بلد المنشأ من بياناتٍ حقيقية الشكل، لا من حقنة إنتاج. top_isos =
    قائمة (m49, iso3) بترتيب تنازلي للقيمة. Seeds the world-export cache so the
    live server serves it offline via the genuine cache path."""
    import silk_data_layer as dl
    from silk_cache import _key
    url = dl.ENDPOINTS["comtrade"]                 # سطح المعاينة (بلا مفتاح)
    params = {"period": str(year), "cmdCode": str(hs_code),
              "flowCode": "X", "partnerCode": "0"}
    data = [{"reporterCode": m49, "reporterISO": iso3,
             "primaryValue": float(10_000_000_000 - i * 1_000_000_000)}
            for i, (m49, iso3) in enumerate(top_isos)]
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, _key(url, params) + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"data": data}, fh)


class LiveShapeServer:
    """مدير سياق يُقلِع uvicorn على DB مبذور ويُغلقه — real uvicorn subprocess.

    `base_url` جاهز بعد `__enter__` (بعد أن يرد /health بـ200). المفاتيح
    المدفوعة غائبة، والتخزين كلّه في مجلّد مؤقّت يُنظَّف عند الخروج."""

    # عيّنة تدفّق ما قبل التشغيل (Wave 1): منتج/سوق/رمز HS يُطلقان استشارةَ بلد
    # المنشأ من مخبأٍ مبذور. الإمارات مُصدِّرٌ حقيقيّ (إعادة تصدير) للتمور —
    # عيّنةٌ مدافَعٌ عنها لا مضلّلة. Deterministic prerun-flow fixture.
    PRERUN_PRODUCT = "تمور"
    PRERUN_HS = "080410"
    PRERUN_MARKET_ISO3 = "ARE"

    # بذر منصّة حتمي لرُتبة ٣ (متوافق مع سياسة كلمات المرور: ٨+ بحرفين ورقم).
    PLATFORM_ADMIN_EMAIL = "admin@silk.local"
    PLATFORM_FACTORY_EMAIL = "owner@factory-a.local"
    PLATFORM_PASSWORD = "Rung3Pass1"

    def __init__(self, port: int | None = None, boot_timeout: float = 45.0,
                 prerun_flags: bool = False, readiness_panel: bool = False,
                 platform: bool = False, env: dict | None = None):
        self.port = port or _free_port()
        self.boot_timeout = boot_timeout
        # لوحة الجاهزية (D) تستلزم صمّامات ما قبل التشغيل + المخبأ المبذور.
        self.prerun_flags = prerun_flags or readiness_panel
        self.readiness_panel = readiness_panel
        # منصّة المصانع (رُتبة ٣ للمنصّة): يبذر قاعدة platform.db المؤقتة
        # بالتثبيتة القياسية قبل الإقلاع كي ينقر المتصفّح دخولاً حقيقياً.
        self.platform = platform
        # تجاوزاتُ بيئةٍ صريحة لتدفّقٍ بعينه — تُطبَّق **أخيراً** فوق كل ما
        # تبنيه `_env`. قيمةٌ فارغة تعني «انزع هذا المتغيّر»، وهو ما يحتاجه
        # تدفّقٌ يريد المقعدَ المحاكى **مطفأً** كي تعمل بوّاباتُ البند فعلاً.
        self.env_overrides = dict(env or {})
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._tmp = tempfile.mkdtemp(prefix="silk_rung2_")
        self.db_path = os.path.join(self._tmp, "silk.db")
        self.cache_dir = os.path.join(self._tmp, "cache")
        self.platform_db = os.path.join(self._tmp, "platform.db")
        self.completed_id = 0
        self.running_id = 0
        self._proc: subprocess.Popen | None = None

    def _env(self) -> dict:
        env = dict(os.environ)
        # كل المخازن على المجلّد المؤقّت — لا تلوّث قرص المطوّر ولا الإنتاج.
        env["SILK_DB"] = self.db_path
        env["SILK_STORE_DB"] = os.path.join(self._tmp, "store.db")
        env["SILK_USAGE_DB"] = os.path.join(self._tmp, "usage.db")
        env["SILK_CACHE_DIR"] = self.cache_dir
        env["SILK_TRACE_DIR"] = os.path.join(self._tmp, "traces")
        # قاعدة المنصّة أيضاً على المؤقّت — بلا هذا كانت `silk_platform.mount`
        # (تعمل على كل إقلاع) تكتب `data/platform.db` الحقيقي في شجرة الريبو
        # أثناء رُتب الاختبار. Platform DB isolated too — mount always runs.
        env["SILK_PLATFORM_DB"] = self.platform_db
        env["SILK_PLATFORM_STORAGE_DIR"] = os.path.join(self._tmp, "files")
        env.pop("SILK_SEED_ADMIN_PASSWORD", None)   # لا بذرَ إقلاعٍ غير مقصود
        # R8 (TEST-1ب/TEST-6، تدقيق 2026-09-01): صمّاماتُ الجلسة التي يطفئها `conftest`
        # للسرعة كانت **ترثها** عمليةُ الخادم، فتُختبَر رُتبتا ٢/٣ على بيئةٍ ليست بيئةَ
        # النشر (بلا مشرفٍ ولا كانسٍ ولا حدِّ معدّل). تُنزَع فتعود لافتراضاتها الإنتاجية،
        # ما لم يمرّرها التدفّقُ صراحةً عبر `env=` (تمرينُ الإعادة يفعل).
        for _sw in _SESSION_SWITCHES:
            env.pop(_sw, None)
        # مقعد المحرّك المحاكى لتدفّق دراسات المنصّة (رُتبة ٣): إطلاق دراسةٍ
        # يعبر مسار الجسر الحقيقي (claim ← حصّة ← خيط) لكن «التحليل» عيّنة
        # موسومة تُحفَظ عبر silk_storage الحقيقي في silk.db المؤقتة — فيلتقط
        # المتصفّح «قيد الإعداد» ثم «مكتملة» بلا أي نداء خارجي.
        # `deep` منذ 2026-08-18: الوضع الإنتاجي الافتراضي صار البحث العميق،
        # فرُتبة المتصفّح تتحقق من شكل نتيجته (عرض deep_research) لا السريع.
        if self.platform:
            env["SILK_PLATFORM_FAKE_ENGINE"] = "deep"
        # وضع تطوير مفتوح مشروع (لا مفاتيح مدفوعة) — الشريط الجانبي يُقرَأ
        # بلا X-API-Key فلا يحتاج المتصفّح لحقن مفتاح. المفاتيح المدفوعة
        # تُنزَع صراحةً كي لا يفلت نداء خارجي في e2e.
        for k in ("SILK_API_KEY", "ANTHROPIC_API_KEY", "SERPER_API_KEY",
                  "COMTRADE_API_KEY", "GOOGLE_MAPS_API_KEY", "EXPLEE_API_KEY",
                  "VOLZA_API_KEY", "SILK_REFRESH_HOURS",
                  "SILK_REQUIRE_PERSISTENT_DATA_DIR"):
            env.pop(k, None)
        env.setdefault("SILK_HTTP_MIN_GAP_MS", "0")
        # تدفّق ما قبل التشغيل (Wave 1): فعّل صمّامات التصنيف/الاستشارة كي تظهر
        # نوافذ التأكيد في المتصفّح. مسار التصنيف الحتمي يعمل بلا مفتاح كلود
        # (CSV)، واستشارةُ بلد المنشأ تقرأ المخبأ المبذور (بلا شبكة).
        if self.prerun_flags:
            env["SILK_HS_CLASSIFIER"] = "1"
            env["SILK_PRODUCER_ADVISORY"] = "1"
            env["SILK_PRODUCER_ADVISORY_TOPN"] = "5"
        # لوحة «جاهزية الدراسة» (D): تفعّل أشقّاء العائلة فتظهر اللوحة الموحّدة
        # في المتصفّح بدل نوافذ الاستشارة التفاعلية المنفردة.
        if self.readiness_panel:
            env["SILK_PRERUN_ADVISORIES"] = "1"
        for k, v in self.env_overrides.items():
            if v:
                env[k] = str(v)
            else:
                env.pop(k, None)
        return env

    def _seed_platform(self) -> None:
        """ابذر قاعدة المنصّة المؤقتة بالتثبيتة القياسية — قبل إقلاع الخادم.

        نفس مسار `silk_platform.seed.seed` الذي تعتمده اختبارات المنصّة
        الهرمتية، بكلمات مرور ثابتة متوافقة مع السياسة تُمرَّر عبر env البذر —
        فيملك تدفّق المتصفّح دخولاً حقيقياً (أدمِن + مصنع) بلا أسرار حية.
        """
        kinds = ("admin", "analyst", "factory_a", "factory_b")
        saved = {k: os.environ.get(f"SILK_SEED_{k.upper()}_PASSWORD")
                 for k in kinds}
        saved_db = os.environ.get("SILK_PLATFORM_DB")
        for kind in kinds:
            os.environ[f"SILK_SEED_{kind.upper()}_PASSWORD"] = self.PLATFORM_PASSWORD
        os.environ["SILK_PLATFORM_DB"] = self.platform_db
        try:
            from silk_platform import db as pdb, seed as pseed
            pdb.init_db(self.platform_db, force=True)
            conn = pdb.connect(self.platform_db)
            try:
                pseed.seed(conn)
                if os.environ.get("SILK_LIVE_SHAPE_SEED_INTERRUPTED") == "1":
                    self._seed_interrupted_study(conn)
            finally:
                conn.close()
        finally:
            # استرجاع مضمون — لا تسرّب بيئةً لبقية اختبارات العملية (الدرس ٥٥).
            for kind in kinds:
                key = f"SILK_SEED_{kind.upper()}_PASSWORD"
                if saved[kind] is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = saved[kind]
            if saved_db is None:
                os.environ.pop("SILK_PLATFORM_DB", None)
            else:
                os.environ["SILK_PLATFORM_DB"] = saved_db

    #: عنوانُ الدراسة المبذورة منقطعةً — يقرؤه تدفّق رُتبة ٣ ليجد صفَّها.
    INTERRUPTED_PRODUCT = "عسل سِدر منقطع"

    def _seed_interrupted_study(self, conn) -> None:
        """ابذر مسودّةً آخرُ محاولتها **انقطعت** — بوّابة R3 لرُتبة ٣.

        شريحةُ «انقطعت» تُشتقّ من `last_run` (لا من `studies.state`)، وهي
        الحالةُ الوحيدة التي لا يبلغها تدفّقُ المتصفّح بنقرةٍ: انقطاعُ إعادة
        النشر يحتاج قتلَ خادمٍ في منتصف تشغيلة. فنبذرها كما يتركها ختمُ
        الإغلاق حرفياً (صفٌّ `interrupted` + `run_error` + مسودّة) — خلفَ
        `SILK_LIVE_SHAPE_SEED_INTERRUPTED=1` فلا تراها بقيةُ التدفّقات.
        """
        now = "2026-08-17T09:00:00+00:00"
        owner = conn.execute(
            "SELECT a.id FROM accounts a JOIN users u ON u.account_id = a.id "
            "WHERE u.email = ?", (self.PLATFORM_FACTORY_EMAIL,)).fetchone()
        if owner is None:                      # بذرٌ تغيّر شكلُه = فشلٌ معلَن
            raise RuntimeError(
                "seed_interrupted: لا حساب لـ" + self.PLATFORM_FACTORY_EMAIL)
        reason = "انقطع التنفيذ بإعادة نشر الخادم — أعد الإطلاق"
        cur = conn.execute(
            "INSERT INTO studies (owner_id, state, product, run_error, "
            "target_count, response_count, created_at, updated_at) "
            "VALUES (?, 'draft', ?, ?, 0, 0, ?, ?)",
            (int(owner[0]), self.INTERRUPTED_PRODUCT, reason, now, now))
        sid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO study_runs (study_id, run_token, state, mode, "
            "params_json, created_at, started_at, finished_at, error_code, "
            "error_text) VALUES (?, ?, 'interrupted', 'quick', '{}', ?, ?, ?, "
            "'interrupted', ?)",
            (sid, f"live-shape-interrupted-{sid}", now, now,
             "2026-08-17T09:05:00+00:00", reason))
        conn.commit()

    def __enter__(self) -> "LiveShapeServer":
        self.seed()
        self.start()
        return self

    def seed(self) -> None:
        """ابذر المخازن المؤقّتة مرّةً — مفصولٌ عن الإقلاع (R2) كي يُعاد تشغيل
        الخادم على **نفس** البيانات في تمرين إعادة النشر."""
        self.completed_id, self.running_id = seed_db(self.db_path)
        if self.platform:
            self._seed_platform()
        if self.prerun_flags:
            # سنةُ الفحص = سنةُ الدراسة − ١ (نفس ما يحسبه حارس الاستشارة حيًّا).
            import datetime as _dt
            year = _dt.date.today().year - 1
            # الإمارات #١ مصدّرًا (عيّنة)، مع مصدّري تمور حقيقيين آخرين.
            seed_producer_export_cache(
                self.cache_dir, self.PRERUN_HS, year,
                [("784", "ARE"), ("788", "TUN"), ("364", "IRN"),
                 ("682", "SAU"), ("368", "IRQ")])

    def start(self) -> "LiveShapeServer":
        """أقلِع uvicorn على المخازن الحالية وانتظر `/health` — يُكرَّر بعد `stop()`."""
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api:app",
             "--host", "127.0.0.1", "--port", str(self.port), "--log-level",
             "warning"],
            cwd=_ROOT, env=self._env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if not self._wait_healthy():
            out = b""
            with contextlib.suppress(Exception):
                if self._proc and self._proc.stdout:
                    out = self._proc.stdout.read(4000)
            self.__exit__(None, None, None)
            raise RuntimeError(
                "rung-2 server did not become healthy in "
                f"{self.boot_timeout}s — server output:\n"
                f"{out.decode('utf-8', 'replace')}")
        return self

    def _wait_healthy(self) -> bool:
        deadline = time.time() + self.boot_timeout
        while time.time() < deadline:
            if self._proc and self._proc.poll() is not None:
                return False  # مات مبكّراً
            try:
                with urllib.request.urlopen(
                        self.base_url + "/health", timeout=3) as r:
                    if r.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                time.sleep(0.3)
        return False

    def stop(self, *, timeout: float = 10.0) -> None:
        """أوقف الخادم برفق والبياناتُ باقية لإقلاعٍ لاحق (R2).

        على لينكس `terminate()` = SIGTERM فيجري حدثُ الإغلاق (ختم «انقطعت»)؛
        على ويندوز هو إنهاءٌ قسريّ — فالتعافي هناك عبر النبضة المنقطعة وحدها.
        """
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            with contextlib.suppress(Exception):
                self._proc.wait(timeout=timeout)
            if self._proc.poll() is None:
                self._proc.kill()
                with contextlib.suppress(Exception):
                    self._proc.wait(timeout=5)
        self._proc = None

    def kill(self) -> None:
        """اقتل الخادم فوراً (SIGKILL) — لا حدث إغلاق؛ يحاكي OOM/سقوطاً مفاجئاً."""
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
            with contextlib.suppress(Exception):
                self._proc.wait(timeout=5)
        self._proc = None

    def __exit__(self, *exc) -> None:
        self.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="رُتبة ٢ — خادم حقيقي مبذور")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--hold", action="store_true",
                    help="أبقِ الخادم معلّقاً للتصفّح اليدوي (Ctrl-C للإيقاف)")
    a = ap.parse_args()
    with LiveShapeServer(port=a.port) as srv:
        print(json.dumps({
            "base_url": srv.base_url,
            "completed_id": srv.completed_id,
            "running_id": srv.running_id,
            "db_path": srv.db_path,
        }, ensure_ascii=False))
        sys.stdout.flush()
        if a.hold:
            print(f"→ افتح {srv.base_url} في المتصفّح — Ctrl-C للإيقاف",
                  file=sys.stderr)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
