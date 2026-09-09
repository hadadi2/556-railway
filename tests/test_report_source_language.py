from silk_i18n import entity_allowlist, foreign_prose_spans


def source_view():
    return {'deep_research': {'missions': {'agreements': {'findings': [
        {'value': 1, 'source': 'GAFTA secretariat، OIC secretariat',
         'source_ids': ['GAFTA secretariat', 'OIC secretariat']},
        {'value': 1, 'source': 'Google Trends'},
        {'value': 1, 'source': 'IMF WEO'},
    ]}}}}


def test_document_source_names_are_exempt_individually_after_reference_formatting():
    allow = entity_allowlist(source_view())
    assert 'GAFTA secretariat' in allow
    assert 'OIC secretariat' in allow
    assert foreign_prose_spans(
        'المصادر: GAFTA secretariat، Google Trends، IMF WEO، OIC secretariat',
        'ar', allow) == []


def test_source_entities_do_not_exempt_actual_foreign_prose():
    assert foreign_prose_spans(
        'GAFTA secretariat supports exports and regulates market access.',
        'ar', entity_allowlist(source_view()))
