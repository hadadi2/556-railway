"""Export the approved pages as one offline HTML file; never rewrite sources.

Prices are a dated snapshot of checked-in configuration, not account data.
Node executes only the shared price formatter, with no browser or network.
"""
from __future__ import annotations

import argparse
import base64
from datetime import date
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Expected one source marker: {old[:70]}")
    return text.replace(old, new, 1)


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def pricing_snapshot() -> dict:
    from silk_platform.pricing import public_pricing
    # No database connection or payment-provider configuration enters the export.
    with patch("silk_platform.db.connect", side_effect=RuntimeError("offline snapshot")), \
         patch("silk_platform.pricing._payment_config", return_value={}):
        pricing = public_pricing()
    if pricing["source"] != "file":
        raise ValueError("A readable project pricing file is required")
    return {k: pricing[k] for k in ("currency", "tiers", "annual_discount_pct")}


def prerender_cards(js: str, pricing: dict) -> str:
    """Use the production formatter so no-JS cards match interactive cards."""
    dictionaries = js[js.index("var L_EN ="):js.index("var LANG =")]
    renderer = js[js.index("function txt("):js.index('if (document.getElementById("plansGrid"))')]
    # This is a string serializer, not a DOM/browser implementation.
    harness = r'''
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
class Element {
  constructor(tag='div') {this.tag=tag;this.children=[];this.attrs={};this.value='';this.classList={add(){},remove(){},toggle(){}};}
  appendChild(child) {this.children.push(child);return child;}
  set textContent(value) {this.children=[];this.value=String(value);}
  setAttribute(key,value) {this.attrs[key]=String(value);}
  html() {
    const attrs={...this.attrs};
    if(this.className) attrs.class=this.className;
    if(this.href) attrs.href=this.href;
    return '<'+this.tag+Object.entries(attrs).map(([k,v])=>' '+k+'="'+esc(v)+'"').join('')+'>'+esc(this.value)+this.children.map(c=>c.html()).join('')+'</'+this.tag+'>';
  }
}
const ids={plansGrid:new Element(),pricingMsg:new Element(),billMonthly:new Element(),billAnnual:new Element()};
const document={getElementById:id=>ids[id],createElement:tag=>new Element(tag)};
var LANG='ar', _cycle='monthly';
'''
    script = harness + dictionaries + renderer + "\nrenderPlans(" + json.dumps(pricing) + ");\n"
    script += "process.stdout.write(ids.plansGrid.children.map(c=>c.html()).join(''));"
    result = subprocess.run(["node", "-"], input=script, text=True,
                            capture_output=True, check=True, timeout=15)
    return result.stdout


class LocalDocument(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.fragments: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id":
                self.ids.append(value)
            if key in ("src", "href") and value:
                if not value.startswith(("data:", "#")):
                    raise ValueError(f"External dependency in export: {value}")
                if value.startswith("#"):
                    self.fragments.append(value[1:])


def build_preview(factory: Path, admin: Path, snapshot_date: date) -> str:
    landing = (ROOT / "web/platform-landing.html").read_text(encoding="utf-8")
    prices = (ROOT / "web/pricing.html").read_text(encoding="utf-8")
    js = (ROOT / "web/marketing.js").read_text(encoding="utf-8")
    pricing = pricing_snapshot()
    js = replace_once(js,
        'a.href = "/checkout.html?plan=" + encodeURIComponent(t.key) +\n             (hasAnnual ? "&cycle=annual" : "");',
        'a.href = "#preview-note";')
    js = replace_once(js, 't.price > 0 ? T.choose : T.start',
                      'LANG === "en" ? "Plan preview" : "معاينة الباقة"')
    cards = prerender_cards(js, pricing)
    start = js.index('if (document.getElementById("plansGrid")) {')
    end = js.index("/* ═══ الظهور بالتمرير", start)
    js = js[:start] + "_plansCache = " + json.dumps(pricing, ensure_ascii=False) + ";\nrenderPlans(_plansCache);\n" + js[end:]

    head = landing.split("<body>")[0]
    nav = landing[landing.index('<nav class="top"'):landing.index('<header class="hero">')]
    content = landing[landing.index('<header class="hero">'):landing.index('<footer>')]
    content = replace_once(content, '<header class="hero">', '<header class="hero" id="landing">')
    price_content = prices[prices.index('<main class="pricing-page">'):prices.index('<footer>')]
    price_content = replace_once(price_content,
        '<div class="plans" id="plansGrid" aria-busy="true"></div>',
        '<div class="plans" id="plansGrid" aria-busy="false">' + cards + '</div>')
    footer = landing[landing.index('<footer>'):landing.index('<script src=')]

    font_source = (ROOT / "web/fonts/fonts.css").read_text(encoding="utf-8")
    font_rules = re.findall(r"@font-face\{[^}]+\}", font_source)
    font_css = "\n".join(rule for rule in font_rules if
                         "font-family:'Cairo'" in rule or "font-family:'IBM Plex Mono'" in rule)
    font_css = re.sub(r"url\('([^']+)'\)", lambda match:
        "url('" + data_uri(ROOT / "web/fonts" / match[1], "font/woff2") + "')", font_css)
    head = replace_once(head, '<link href="/fonts/fonts.css" rel="stylesheet">', '<style>' + font_css + '</style>')
    motion_css = (ROOT / "web/research-motion.css").read_text(encoding="utf-8")
    head = replace_once(head, '<link href="/research-motion.css" rel="stylesheet">', '<style>' + motion_css + '</style>')
    extra = '''<style>
.portable-tabs{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;padding:14px;background:#fff;border-bottom:1px solid #e2e8f0}
.portable-tabs a{padding:8px 16px;border-radius:30px;background:#edf4ff;color:#183255;font-size:14px}
.reference-screen{padding:32px 22px;max-width:1280px;margin:auto}
.reference-screen img{display:block;width:100%;height:auto;border-radius:16px}
.reference-screen h2{text-align:center;font-size:26px;margin-bottom:12px}
.reference-screen p{text-align:center;color:#64748b;margin-bottom:22px}
.preview-note{padding:14px 22px;font-size:13px;text-align:center;color:#475569;background:#f8fafc}
#landing,#pricing,.reference-screen,#preview-note{scroll-margin-top:90px}
</style>'''
    notes = '<div id="preview-note" class="preview-note">معاينة التصميم · الأسعار من إعدادات المشروع بتاريخ ' + snapshot_date.isoformat() + '. لوحتا المصنع والإدارة أدناه صور للتصميم المعتمد، وليستا بيانات حساب مباشر.</div>'
    notes += '<noscript><style>.bill-toggle,#langBtn,#menuBtn{display:none}</style><p class="preview-note">الأسعار المعروضة شهرية، ويظهر إجمالي الاشتراك السنوي تحت كل باقة مدفوعة.</p></noscript>'
    tabs = '<nav class="portable-tabs" aria-label="صفحات المعاينة"><a href="#landing">صفحة الهبوط</a><a href="#pricing">الأسعار</a><a href="#factory-preview">تصميم المصنع</a><a href="#admin-preview">تصميم الإدارة</a></nav>'
    references = ""
    for name, label, path in [("factory", "المصنع", factory), ("admin", "الإدارة", admin)]:
        title = escape("تصميم لوحة " + label)
        references += '<section id="' + name + '-preview" class="reference-screen"><h2>' + title + '</h2><p>مرجع التصميم المعتمد — بيانات توضيحية</p><img src="' + data_uri(path, "image/png") + '" alt="' + title + '"></section>'
    html = head.replace('</head>', extra + '</head>') + '<body>' + nav + notes + tabs + content + price_content + references + footer + '<script>' + js + '</script></body></html>'
    html = html.replace('href="/pricing.html"', 'href="#pricing"').replace('href="/platform.html"', 'href="#preview-note"')
    html = re.sub(r'src="(/[^\"]+\.png)"', lambda match:
                  'src="' + data_uri(ROOT / "web" / match[1].lstrip('/'), 'image/png') + '"', html)
    html = replace_once(html, '<title>سِلك للدراسات</title>', '<title>سلك — المعاينة الكاملة</title>')
    document = LocalDocument()
    document.feed(html)
    if len(document.ids) != len(set(document.ids)) or set(document.fragments) - set(document.ids):
        raise ValueError("Duplicate anchors or broken local links")
    if 'fetch(' in html:
        raise ValueError("Offline preview must not request remote data")
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--factory-reference', type=Path, required=True)
    parser.add_argument('--admin-reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--date', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    html = build_preview(args.factory_reference, args.admin_reference, args.date)
    args.output.write_text(html, encoding='utf-8')
    print(json.dumps({'file': str(args.output.resolve()), 'bytes': args.output.stat().st_size}))


if __name__ == '__main__':
    main()
