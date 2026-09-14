
"use strict";
document.documentElement.className += " js";
var REDUCED = window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ═══ اللغة: العربية مؤلَّفة في الترميز؛ الإنجليزية تُطبَّق وقت التشغيل ═══ */
var L_EN = {
  tag: "Market studies",
  navFeat: "Features",
  navPricing: "Plans",
  cta: "Start now",
  login: "Sign in",
  eyebrow: "Silk market studies",
  h1: "Understand your product’s prospects<br>before entering the market.",
  hsub: "Assess demand, competition and entry requirements before you start exporting.",
  ctaStudy: "Start your study",
  discover: "What does the study cover?",
  previewCaption: "Illustrative platform preview",
  researchTitle: "12 agents working on your study",
  researchSub: "Each agent researches its specialty. The findings come together in one study.",
  motionPause: "Pause animation",
  studyOutput: "Market study",
  studyType: "A complete view of your product’s prospects",
  studyAnalysis: "Market analysis",
  studyRecommendations: "Opportunities and recommendations",
  studySynthesis: "Connected findings in one study",
  agent_trade_flow: "Trade flows",
  agent_demand_trends: "Demand and seasonality",
  agent_pricing_scout: "Pricing analysis",
  agent_competitors: "Competitor analysis",
  agent_consumer_culture: "Consumer culture",
  agent_demographics_economy: "Population and economy",
  agent_customs_requirements: "Customs requirements",
  agent_tariffs_agreements: "Tariffs and agreements",
  agent_logistics: "Logistics",
  agent_channels_importers: "Distribution channels",
  agent_risk_news: "Risks and developments",
  agent_opportunity_gaps: "Strategic opportunities",
  fT: "A clearer view of your target market.",
  fS: "Explore what affects your sales prospects and the cost of market entry.",
  f1t: "Sales opportunities",
  f1b: "Understand demand and its trends in your target market.",
  f2t: "Competition and pricing",
  f2b: "Explore competing products, prices and distribution channels.",
  f3t: "Entry requirements",
  f3b: "Review requirements, tariffs and barriers before exporting.",
  opTitle: "Discover where your product has an opportunity.",
  opIntro: "Enter a six-digit HS code to see the top three markets in ITC data before starting a market study.",
  opScope: "The preview shows market rankings only. An account unlocks USD values and unrealized potential.",
  opLabel: "Product HS code",
  opSearch: "Show top markets",
  opLocked: "Sign in to see USD values and unrealized potential.",
  opReveal: "I have an account — show values",
  opNew: "New user — request a free account",
  opSource: "Source: ITC Export Potential Map · 2030 estimates · post-login values use USD and English numerals.",
  proofT: "Trusted sources to help you assess the opportunity before investing.",
  bandT: "Which market fits your product?",
  bandS: "Choose your product and target market to start the study.",
  firstStudy: "Create your first study",
  footer: "Silk · Studies that support your decisions.",
  prT: "Plans and pricing",
  prS: "Compare study allowances and features to choose the right plan for your factory.",
  activation: "Subscriptions and upgrades are activated by the Silk team.",
  payment: "Online payment integration is in progress.",
  faqT: "Before you subscribe",
  q1: "Does the free study renew?",
  a1: "The Basic plan includes one trial study for the lifetime of the account.",
  q2: "How is annual billing calculated?",
  a2: "Select Annual to see the monthly equivalent and total annual charge before requesting a subscription.",
  q3: "How do I upgrade?",
  a3: "Choose your plan and submit a subscription request. The Silk team will follow up on activation.",
  helpT: "Try the platform with a free study.",
  helpS: "Explore what a study includes before choosing your subscription.",
  /* بطاقات الباقات (تُبنى بالجافاسكربت) */
  perMonth: "SAR / month",
  free: "Free",
  trial: "One trial study (lifetime)",
  exportR: "Report export",
  api: "API access",
  wlabel: "White label",
  choose: "Choose this plan",
  start: "Start free",
  billM: "Monthly",
  billA: "Annual",
  prFail: "Could not load prices right now — contact us and we will send you the plan sheet.",
  monthly: function (n) { return n + (n === 1 ? " study per month" : " studies per month"); },
  savePct: function (p) { return "Save " + p + "%"; },
  billedAnnually: function (v) { return "billed annually — " + v + " SAR"; },
  names: {basic: "Basic", silver: "Silver", gold: "Gold", platinum: "Platinum"},
};
var L_AR = {
  perMonth: "ر.س / شهرياً",
  free: "مجاناً",
  trial: "دراسة تجريبية واحدة (مدى الحياة)",
  monthly: function (n) {
    if (n === 1) return "دراسة واحدة شهرياً";
    if (n === 2) return "دراستان شهرياً";
    return n + (n % 100 >= 3 && n % 100 <= 10 ? " دراسات شهرياً" : " دراسة شهرياً");
  },
  exportR: "تصدير التقارير",
  api: "وصول برمجي API",
  wlabel: "علامة بيضاء",
  choose: "اختر هذه الباقة",
  start: "ابدأ مجاناً",
  billM: "شهري",
  billA: "سنوي",
  savePct: function (p) { return "وفّر " + p + "%"; },
  billedAnnually: function (v) { return "تُدفع سنوياً — " + v + " ر.س"; },
  prFail: "تعذّر تحميل الأسعار الآن — تواصل معنا وسنرسل لك جدول الباقات.",
  names: {basic: "أساسية", silver: "فضية", gold: "ذهبية", platinum: "بلاتينية"},
};

var LANG = "ar";
var AR_ORIG = {};   // النص العربي المؤلَّف — يُلتقط من الصفحة نفسها (لا نسخ ثانٍ)
document.querySelectorAll("[data-i18n]").forEach(function (el) {
  var k = el.getAttribute("data-i18n");
  if (!(k in AR_ORIG)) {
    AR_ORIG[k] = el.getAttribute("data-i18n-html") ? el.innerHTML : el.textContent;
  }
});

function applyLang(lang) {
  LANG = lang === "en" ? "en" : "ar";
  try { localStorage.setItem("silk_lang", LANG); } catch (e) { /* خصوصية */ }
  document.documentElement.lang = LANG;
  document.documentElement.dir = LANG === "en" ? "ltr" : "rtl";
  document.querySelectorAll("[data-i18n]").forEach(function (el) {
    var k = el.getAttribute("data-i18n");
    var v = LANG === "en" ? L_EN[k] : AR_ORIG[k];
    if (v == null) return;
    if (el.getAttribute("data-i18n-html")) el.innerHTML = v;
    else el.textContent = v;
  });
  document.getElementById("langBtn").textContent =
    LANG === "en" ? "العربية" : "English";
  renderPlans(_plansCache);
  applyAria();
  renderOpportunityPreview();

}
/* أوصاف الوصول (aria-label) خارج آلية data-i18n النصية — تُبدَّل هنا. */
var ARIA = {
  menuBtn: {ar: "القائمة", en: "Menu"},
  carPrev: {ar: "السابق", en: "Previous"},
  carNext: {ar: "التالي", en: "Next"},
};
function applyAria() {
  Object.keys(ARIA).forEach(function (id) {
    var el = document.getElementById(id);
    if (el) el.setAttribute("aria-label", ARIA[id][LANG]);
  });
  document.querySelectorAll("#carDots .cdot").forEach(function (d, i) {
    d.setAttribute("aria-label",
      (LANG === "en" ? "Slide " : "شريحة ") + (i + 1));
  });
}
document.getElementById("langBtn").onclick = function () {
  applyLang(LANG === "en" ? "ar" : "en");
};

/* ═══ الشريط العلوي: قائمة الجوال + ظلّ عند التمرير ═══════════════════════ */
(function nav() {
  var btn = document.getElementById("menuBtn");
  var menu = document.getElementById("mobileMenu");
  var bar = document.getElementById("topNav");
  btn.onclick = function () {
    var open = menu.classList.toggle("open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  };
  menu.addEventListener("click", function (e) {
    var t = e.target;
    while (t && t !== menu && t.tagName !== "A") t = t.parentNode;
    if (t && t.tagName === "A") {
      menu.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
    }
  });
  function onScroll() {
    bar.classList.toggle("scrolled", window.scrollY > 4);
  }
  window.addEventListener("scroll", onScroll, {passive: true});
  onScroll();
})();

/* Research illustration: no API calls, timers, fabricated results or progress. */
(function researchMotion() {
  var scene = document.getElementById("researchMotion");
  var button = document.getElementById("researchPause");
  if (!scene || !button) return;
  var preference = window.matchMedia("(prefers-reduced-motion: reduce)");
  var paused = false;
  var visible = true;
  function sync() {
    scene.setAttribute("data-motion", paused || preference.matches || document.hidden || !visible ? "paused" : "playing");
    button.setAttribute("aria-pressed", String(paused || preference.matches));
    button.disabled = preference.matches;
  }
  button.hidden = false;
  button.onclick = function () { paused = !paused; sync(); };
  if (preference.addEventListener) preference.addEventListener("change", sync);
  document.addEventListener("visibilitychange", sync);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      visible = entries.some(function (entry) { return entry.isIntersecting; });
      sync();
    }).observe(scene);
  }
  sync();
})();

/* ═══ الباقات — من GET /platform/pricing حصراً (لا سعر مثبّت هنا) ═════════ */
var _plansCache;   // undefined = الجلب لم يصل بعد؛ null = فشل معلَن
var _cycle = "monthly";   // دورة العرض المختارة — يقلبها مبدّل شهري/سنوي
(function billToggle() {
  var bm = document.getElementById("billMonthly");
  var ba = document.getElementById("billAnnual");
  if (!bm || !ba) return;
  bm.onclick = function () { _cycle = "monthly"; renderPlans(_plansCache); };
  ba.onclick = function () { _cycle = "annual"; renderPlans(_plansCache); };
})();
function txt(el, s) { el.textContent = s; return el; }
function renderPlans(data) {
  var grid = document.getElementById("plansGrid");
  var msg = document.getElementById("pricingMsg");
  if (!grid || !msg) return;
  var T = LANG === "en" ? L_EN : L_AR;
  var annual = _cycle === "annual";
  // نصّا الزرّين يتبعان اللغة قبل وصول الأسعار ومع فشلها — النسبة تُلحق
  // عند توفّر الرد فقط (مشتقّة خادمياً من الأسعار نفسها).
  var pct = (data && Number(data.annual_discount_pct)) || 0;
  var bm = document.getElementById("billMonthly");
  var ba = document.getElementById("billAnnual");
  if (bm && ba) {
    txt(bm, T.billM);
    txt(ba, T.billA + (pct > 0 ? " — " + T.savePct(pct) : ""));
    bm.classList.toggle("on", !annual);
    ba.classList.toggle("on", annual);
    bm.setAttribute("aria-pressed", String(!annual));
    ba.setAttribute("aria-pressed", String(annual));
  }
  grid.textContent = "";
  if (!data || !data.tiers || !data.tiers.length) {
    if (data === undefined) { txt(msg, LANG === "en" ? "Loading plans…" : "جارٍ تحميل الباقات…"); return; } //              // لم يصل الجلب بعد
    grid.setAttribute("aria-busy", "false");
    msg.classList.add("on");
    txt(msg, T.prFail);
    return;
  }
  msg.classList.remove("on"); msg.textContent = ""; grid.setAttribute("aria-busy", "false");
  data.tiers.forEach(function (t) {
    var d = document.createElement("div");
    d.className = "plan" + (t.key === "gold" ? " hot" : "");

    var icon = document.createElement("span"); icon.className = "plan-icon"; icon.setAttribute("aria-hidden", "true"); d.appendChild(icon);
    var h = document.createElement("h3");
    d.appendChild(txt(h, T.names[t.key] || t.key));
    var pr = document.createElement("div");
    pr.className = "price";
    var b = document.createElement("b");
    b.className = "num";
    var span = document.createElement("span");
    var hasAnnual = annual && t.price > 0 && t.price_annual > 0;
    if (t.price > 0) {
      // السنوي يُعرض بمكافئه الشهري (السنوي ÷ 12) + سطر الإجمالي السنوي
      txt(b, Number(hasAnnual ? (t.price_annual / 12)
                              : t.price).toLocaleString("en", {maximumFractionDigits: 2}));
      txt(span, T.perMonth);
    } else { txt(b, T.free); }
    pr.appendChild(b); pr.appendChild(span); d.appendChild(pr);
    if (t.price > 0 && t.price_annual > 0) {
      var ab = document.createElement("div");
      ab.className = "abill";
      d.appendChild(txt(ab,
        hasAnnual ? T.billedAnnually(Number(t.price_annual).toLocaleString("en"))
          : (LANG === "en" ? "Or " : "أو ") + Number(t.price_annual).toLocaleString("en") + (LANG === "en" ? " SAR annually" : " ر.س سنوياً")));
    }
    var ul = document.createElement("ul");
    var items = [];
    if (t.monthly_studies > 0) items.push(T.monthly(t.monthly_studies));
    else if (t.lifetime_studies > 0) items.push(T.trial);
    if (t.dashboard === "full") items.push(LANG === "en" ? "Full dashboard" : "لوحة متابعة متكاملة");
    else if (t.dashboard === "basic") items.push(LANG === "en" ? "Basic dashboard" : "لوحة متابعة أساسية");
    else if (t.dashboard === "none") items.push(LANG === "en" ? "No overview dashboard" : "دون لوحة متابعة");
    if (t.export) items.push(T.exportR);
    if (t.api_access) items.push(T.api);
    if (t.white_label) items.push(T.wlabel);
    items.forEach(function (s) {
      var li = document.createElement("li");
      ul.appendChild(txt(li, s));
    });
    d.appendChild(ul);
    var a = document.createElement("a");
    a.className = "btn" + (t.key === "gold" ? "" : " gh");
    a.href = "/checkout.html?plan=" + encodeURIComponent(t.key) +
             (hasAnnual ? "&cycle=annual" : "");
    d.appendChild(txt(a, t.price > 0 ? T.choose : T.start));
    grid.appendChild(d);
  });
}
if (document.getElementById("plansGrid")) {
renderPlans(undefined);
fetch("/platform/pricing").then(function (r) {
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}).then(function (data) { _plansCache = data; renderPlans(data); })
  .catch(function () { _plansCache = null; renderPlans(null); });
}

/* ═══ معاينة فرص التصدير العامة — أسماء وترتيب فقط، بلا قيم خام ═══════ */
var _opportunityPreviewData = null;
function opText(ar, en) { return LANG === "en" ? en : ar; }
function normalizeHs(value) {
  return String(value || "").replace(/[٠-٩]/g, function (c) {
    return String("٠١٢٣٤٥٦٧٨٩".indexOf(c));
  }).replace(/[۰-۹]/g, function (c) {
    return String("۰۱۲۳۴۵۶۷۸۹".indexOf(c));
  }).replace(/\D/g, "").slice(0, 6);
}
function recordOpportunityEvent(kind, hs) {
  fetch("/platform/export-opportunities/public-event", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({kind: kind, hs_code: hs || ""}), keepalive: true
  }).catch(function () { /* analytics never blocks the visitor */ });
}
function renderOpportunityPreview() {
  var data = _opportunityPreviewData;
  var result = document.getElementById("opportunityResult");
  if (!data || !result) return;
  var product = document.getElementById("opportunityProduct");
  var markets = document.getElementById("opportunityMarkets");
  var name = LANG === "ar" && data.product.name_ar ? data.product.name_ar : data.product.name;
  product.textContent = opText("المنتج: ", "Product: ") + name + " · HS " + data.product.hs_code;
  markets.textContent = "";
  data.markets.forEach(function (market) {
    var li = document.createElement("li");
    var rank = document.createElement("span"); rank.className = "opportunity-rank"; rank.textContent = String(market.rank);
    var label = document.createElement("span"); label.textContent = LANG === "ar" && market.name_ar ? market.name_ar : market.name;
    li.appendChild(rank); li.appendChild(label); markets.appendChild(li);
  });
  var query = "opportunity_hs=" + encodeURIComponent(data.product.hs_code) +
    "&opportunity_name=" + encodeURIComponent(name);
  document.getElementById("opportunityLogin").href = "/platform.html?" + query;
  document.getElementById("opportunitySignup").href = "/checkout.html?plan=basic&" + query;
  result.hidden = false;
}
(function opportunityExplorer() {
  var form = document.getElementById("opportunityForm");
  if (!form) return;
  var input = document.getElementById("opportunityHs");
  var status = document.getElementById("opportunityStatus");
  var submit = document.getElementById("opportunitySubmit");
  input.addEventListener("input", function () { input.value = normalizeHs(input.value); });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var hs = normalizeHs(input.value); input.value = hs;
    recordOpportunityEvent("search_started", /^\d{6}$/.test(hs) ? hs : "");
    status.className = "opportunity-status";
    if (!/^\d{6}$/.test(hs)) {
      status.textContent = opText("أدخل رمز HS صحيحًا من 6 أرقام.", "Enter a valid six-digit HS code.");
      status.classList.add("error"); input.focus(); return;
    }
    submit.disabled = true; status.textContent = opText("جارٍ جلب بيانات ITC…", "Retrieving ITC data…");
    fetch("/platform/export-opportunities/preview?hs_code=" + encodeURIComponent(hs))
      .then(function (response) {
        if (response.ok) return response.json();
        var messages = response.status === 404
          ? opText("لم نجد هذا الرمز في كتالوج المنتجات أو لدى ITC.", "This code was not found in the product catalog or ITC.")
          : response.status === 429
            ? opText("طلبات كثيرة. انتظر دقيقة ثم أعد المحاولة.", "Too many requests. Wait a minute and try again.")
            : opText("تعذر جلب بيانات ITC الآن، ولم نعرض بيانات بديلة.", "ITC data is unavailable, and no substitute data was shown.");
        throw new Error(messages);
      }).then(function (data) {
        _opportunityPreviewData = data; status.textContent = ""; renderOpportunityPreview();
      }).catch(function (error) {
        _opportunityPreviewData = null; document.getElementById("opportunityResult").hidden = true;
        status.textContent = error.message; status.classList.add("error");
      }).finally(function () { submit.disabled = false; });
  });
  document.getElementById("opportunityLogin").addEventListener("click", function () {
    recordOpportunityEvent("signup_clicked", _opportunityPreviewData && _opportunityPreviewData.product.hs_code);
  });
  document.getElementById("opportunitySignup").addEventListener("click", function () {
    recordOpportunityEvent("subscription_clicked", _opportunityPreviewData && _opportunityPreviewData.product.hs_code);
  });
})();


/* ═══ الظهور بالتمرير — يتعطّل كلياً مع تفضيل تقليل الحركة ═══════════════ */
(function reveal() {
  var els = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));
  if (REDUCED || !("IntersectionObserver" in window)) {
    els.forEach(function (el) { el.classList.add("in"); });
    return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) {
        en.target.classList.add("in");
        io.unobserve(en.target);
      }
    });
  }, {threshold: .15});
  els.forEach(function (el) { io.observe(el); });
})();

/* اختيار اللغة المحفوظ (بلا جلسة — الهبوط عامة). */
try {
  if (localStorage.getItem("silk_lang") === "en") applyLang("en");
} catch (e) { /* وضع خصوصية */ }

