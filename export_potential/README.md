# Silk Export Potential

Independent local application using the anonymous chart responses consumed by
ITC Export Potential Map. No Comtrade model, tariff agent, platform database or
platform engine is used for the chart values.

## Operation

Run the platform normally; the chart page is served at /export-potential on the same origin. For a standalone chart service, install xport_potential/requirements.txt and run python -m uvicorn export_potential.app:app --host 127.0.0.1 --port 8003. The page uses relative asset and API URLs.

The optional authenticated dashboard workflow is documented in docs/export-opportunities.md.

## Source contract

`client.py` reads only fixed ITC hosts and validated chart paths. Requests carry
the same public `X-Context: epm2` and `X-Format: camel` headers as the public page.
The public browser transport wrapper is decoded as documented by its shipped
client. No authentication, account credentials, premium API key, paywall, partner
embedding restriction or access-control setting is bypassed.

This is an unofficial integration, not the contracted ITC API. The official
services page describes Excel datasets, API access and embedding as paid products.
No claim is made that anonymous chart access grants a commercial redistribution
license or a supported API contract.

Reference: https://exportpotential.intracen.org/en/our-services
Source data: https://exportpotential.intracen.org/en/resources/data-sources

Mappings verified against the current page implementation on 2026-09-12:

| Silk field | ITC field / chart expression |
|---|---|
| potential | value |
| baseline | exportValue |
| unrealized | value × (1 − realizedPotential) |
| realized ratio | realizedPotential |
| demand | bubbleSize |
| ease | lineWidth |
| supply | lineLength |

Raw fields are retained alongside the display contract. Missing values stay null.
Unrealized aggregate potential is not recomputed as potential minus aggregate
baseline exports. Economy IDs are ITC IDs: India is 699 and the US is 842 in this
catalogue, so substituting local M49 IDs would be incorrect.

Country/sub-region/region and product/sub-sector/sector aggregations are requested
from ITC rather than constructed from a truncated subset. The catalogue currently
contains 226 economies and 4,658 ITC product groups. The chart year is retrieved
from ITC's dictionary. The trade period 2020–2024 was verified for the 2030 release
on 2026-09-12; it is not presented for a different projection year.

Responses are cached in memory for up to 15 minutes, with a maximum of 40 entries.
Every dataset carries its source URL, retrieval timestamp and response SHA-256.
Network or schema errors clear the chart; there is no estimation fallback.
CSV downloads require the same source response revision as the displayed chart.

## UI and tests

Arabic/English, RTL/LTR, three analysis axes, original product grouping IDs,
geographic circles, gap and radial charts, sorting, top N, independent list search,
manual selection, shareable state URLs, details and CSV downloads are implemented.
Summary cards cover all returned results; the selection count describes the plot.
Untranslated source names retain their official English labels.

Run `python -m pytest tests/test_export_potential.py tests/test_export_opportunities.py`.
Browser checks covered both languages, top 5 plus one selected market, URL
restoration of six selections, clear-all, the charts and Saudi Arabia → Yemen
product selection. HTTP checks covered all three axes, World/all products,
15 sub-regions, 5 regions, retirement of the new service's estimate route, and
the actual downloadable CSV response including exact values and provenance.

The retired estimate route returns 410. No numeric parity claim is made for
untested ITC views, product diversification, services trade or partner embedding.
