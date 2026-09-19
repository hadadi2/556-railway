"""Conservative validation of collected contacts, including saved results."""
import re

_US_ADDRESS = re.compile(
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\s+\d{5}(?:-\d{4})?\b")
_PLACEHOLDER_EMAILS = {"email@email.com", "user@domain.com", "name@domain.com",
                       "your@email.com", "yourname@email.com", "test@test.com"}
_PLACEHOLDER_DOMAINS = {
    "example.com", "example.org", "example.net", "example.edu",
    # الدرس ٢٦٣ (بلاغ المالك: «احذف البيانات الافتراضية مثل mysite.com»):
    # نطاقاتُ القوالب الجاهزة تصل من الكشط كأنها موقعُ الشركة. القائمةُ
    # **مغلقةٌ ومسمّاة** — لا حدسَ على نطاقٍ حقيقيّ قد يشبهها.
    "mysite.com", "yoursite.com", "yourdomain.com", "domain.com",
    "website.com", "yourwebsite.com", "sitename.com", "mywebsite.com",
    "examplesite.com", "test.com", "localhost",
}
#: مضيفاتٌ لا تُحلّ إلى موقعٍ عامّ أصلاً — تُعامَل نائبةً كذلك.
_PLACEHOLDER_SUFFIXES = (".local", ".localhost", ".internal", ".invalid",
                         ".test", ".example")


def _host(url: str) -> str:
    """مضيفُ الرابط بلا بروتوكول ولا www ولا مسار — بلا تبعيةٍ خارجية."""
    h = str(url or "").strip().lower()
    for pre in ("https://", "http://", "//"):
        if h.startswith(pre):
            h = h[len(pre):]
    h = h.split("/")[0].split("?")[0].split("#")[0]
    if "@" in h:
        h = h.rsplit("@", 1)[-1]
    h = h.split(":")[0]
    return h[4:] if h.startswith("www.") else h


def is_placeholder_site(url: object) -> bool:
    """هل هذا «موقعٌ» نائبٌ من قالبٍ جاهز لا موقعَ شركة؟ (الدرس ٢٦٣)

    القاعدةُ مغلقة: نطاقٌ مسمّى في القائمة، أو لاحقةٌ لا تُحلّ عمومياً، أو
    مضيفٌ بلا نقطةٍ إطلاقاً. ما عدا ذلك يمرّ — لا يُحذَف موقعٌ حقيقيّ بالحدس.
    """
    host = _host(url)
    if not host:
        return False
    if host in _PLACEHOLDER_DOMAINS or host.endswith(_PLACEHOLDER_SUFFIXES):
        return True
    return "." not in host


def clean_contact(lead, target_iso3=""):
    """Remove demonstrably foreign rows and placeholder email/website values;
    never guess."""
    if not isinstance(lead, dict):
        return None
    result = dict(lead)
    address = str(result.get("address") or "")
    target = str(target_iso3 or "").upper()
    if target and target != "USA" and _US_ADDRESS.search(address):
        return None
    email = str(result.get("email") or "").strip()
    domain = email.rsplit("@", 1)[-1].lower()
    if (email.lower() in _PLACEHOLDER_EMAILS or
            domain in _PLACEHOLDER_DOMAINS):
        result["email"] = ""
    # الدرس ٢٦٣: حقلُ الموقع كان بلا مِصفاةِ نائبٍ إطلاقاً (البريدُ وحدَه
    # محروس)، فيصل «mysite.com» جدولَ العميل ويُعَدّ اتصالاً يُبقي الصفّ.
    if is_placeholder_site(result.get("website")):
        result["website"] = ""
    return result
