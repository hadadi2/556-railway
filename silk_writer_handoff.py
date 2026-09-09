"""One evidence bundle for the writer and reviewer; preserve mission failures."""
from silk_agents import AgentReport
from silk_data_layer import DataPoint
from silk_gmaps import maps_disclaimer


def writer_reports(missions, importer_leads=None, product="", lang="ar", market=""):
    from silk_search_index_evidence import normalized_reports
    from silk_product_evidence import price_reports
    reports = price_reports(normalized_reports(missions), product)
    if not isinstance(importer_leads, dict):
        return reports
    from silk_contact_quality import clean_contact
    from silk_market_resolver import resolve_market
    market_ref, _ = resolve_market(market) if market else (None, None)
    target_iso3 = getattr(market_ref, "iso3", "")
    rows = importer_leads.get("leads") or []
    if market_ref is not None:
        from dataclasses import asdict
        from silk_reports import _clean_leads
        rows = _clean_leads(rows, {"market": asdict(market_ref)})
    findings = []
    for row in rows:
        row = clean_contact(row, target_iso3)
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        # Carry only collected fields; a directory listing is not proof of imports.
        value = {k: row.get(k) for k in (
            "name", "category", "address", "phone", "email", "website", "maps_link", "doc_level")
                 if row.get(k) not in (None, "")}
        source = str(row.get("source") or "unverified_contact_candidate")
        findings.append(DataPoint(
            value, source, 0.0,
            maps_disclaimer(product, lang) + " " + str(row.get("doc_level") or ""),
            url=str(row.get("maps_link") or row.get("website") or "")))
    if not findings:
        findings.append(DataPoint(None, "contact_enrichment", 0.0,
                                 str(importer_leads.get("note") or "No contact evidence available.")))
    reports["contact_enrichment"] = AgentReport("contact_enrichment", findings)
    return reports
