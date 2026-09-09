import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_contact_table_uses_structured_rows_and_escapes_external_fields():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable')
    html = (Path(__file__).parents[1] / 'web/platform.html').read_text(encoding='utf-8')
    function = html.split('function potentialClientsHTML(dr) {', 1)[1].split('\nfunction pdfBtn', 1)[0]
    script = '''function esc(v) {return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
function ar_en(ar,en) {return ar;}
function potentialClientsHTML(dr) {''' + function + '\nconsole.log(potentialClientsHTML(' + json.dumps({
        'importer_leads': {'leads': [{'name': '<script>bad</script>', 'phone': '+12345',
            'email': 'office@example.test', 'website': 'javascript:alert(1)',
            'maps_link': 'https://maps.example.test/place'}]}}) + '));'
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert '+12345' in result.stdout and 'office@example.test' in result.stdout
    assert '&lt;script&gt;' in result.stdout and '<script>' not in result.stdout
    assert 'href="javascript:' not in result.stdout
    assert 'https://maps.example.test/place' in result.stdout


def test_browser_and_documents_receive_the_same_filtered_contacts():
    from silk_render import _client_leads
    from silk_reports import _clean_leads
    market = {'iso3': 'JOR', 'name_en': 'Jordan', 'name_ar': 'الأردن'}
    rows = [{'name': 'Local Trading', 'address': 'Amman, Jordan', 'phone': '+123'},
            {'name': 'Other Trading', 'address': 'France', 'phone': '+456'},
            {'name': 'No Contact'}]
    assert _client_leads({'leads': rows}, market)['leads'] == _clean_leads(rows, {'market': market})
