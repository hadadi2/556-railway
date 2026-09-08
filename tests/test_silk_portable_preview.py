"""Offline delivery contract: complete assets/prices, no source mutations."""
from datetime import date
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Preview(HTMLParser):
    def __init__(self):
        super().__init__()
        self.plans = []
        self.buttons = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div' and 'plan' in attrs.get('class', '').split():
            self.plans.append(attrs)
        if tag == 'a' and attrs.get('href') == '#preview-note' and 'btn' in attrs.get('class', '').split():
            self.buttons.append(attrs)
        if tag == 'img':
            self.images.append(attrs['src'])


@pytest.mark.skipif(not shutil.which('node'), reason='The shared price renderer uses Node')
def test_export_contains_readable_cards_without_js_and_does_not_rewrite_sources():
    from tools.export_silk_preview import build_preview, pricing_snapshot
    source_paths = [ROOT/'web'/name for name in
                    ['platform-landing.html', 'pricing.html', 'marketing.js', 'research-motion.css', 'fonts/fonts.css']]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths]
    # Export mechanics are tested with an existing repository image; the actual
    # deliverable is built separately with the owner's two approved references.
    reference = ROOT/'web/silk-approved-preview.png'
    html = build_preview(reference, reference, date(2026, 9, 7))
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths]
    static_markup = html.split('<script>')[0]
    document = Preview()
    document.feed(static_markup)
    assert len(document.plans) == 4
    # Before any script runs, the highlighted card must have a black button.
    plan_section = Preview()
    plan_section.feed(static_markup.split('<div class="plans" id="plansGrid"')[1].split('<div id="pricingMsg"')[0])
    plan_buttons = plan_section.buttons
    assert len(plan_buttons) == 4
    assert [button['class'] for button in plan_buttons] == ['btn gh', 'btn gh', 'btn', 'btn gh']
    for tier in pricing_snapshot()['tiers']:
        if tier['price']:
            assert f'>{tier["price"]:,}<' in static_markup
            assert f'{tier["price_annual"]:,}' in static_markup
    assert 'دراستان شهرياً' in static_markup
    assert '15 دراسة شهرياً' in static_markup
    assert '2 دراسات' not in static_markup
    assert all(src.startswith('data:image/png;base64,') for src in document.images)
    assert 'data:font/woff2;base64,' in static_markup
    assert 'fetch(' not in html
    assert 'href="#landing"' in static_markup
    assert static_markup.count('data-agent="') == 12
    assert 'id="researchMotion"' in static_markup
    for phrase in ['جولة سريعة', 'من اسم المنتج إلى تقرير', 'لا نخمن الأرقام', 'لا نخمّن الأرقام', 'الإمارات']:
        assert phrase not in static_markup
