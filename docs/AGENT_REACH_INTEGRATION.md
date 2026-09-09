# Agent Reach and report evidence

Agent Reach 1.5.0 is pinned to upstream commit
`da5044d26fc6adddb6554d5679c94ac22e76e428`. Its CLI is installed in
`/opt/agent-reach` independently of the platform's Python dependencies.
Installing the package does not configure authenticated social channels.

Set `SEARCH_PROVIDER=agent_reach` to use the public Exa MCP search backend
documented by Agent Reach. `silk_agent_reach_search.py` calls its read-only
`web_search_exa` tool directly using the existing bounded HTTP transport.
The primary backend uses no API key, browser cookie or generated answer.
An optional fallback is enabled only with `SEARCH_FALLBACK_PROVIDER=tavily`
and `TAVILY_API_KEY`. It runs one basic search only after the primary returns
no usable result, preserves Tavily provenance, and leaves both failures
visible when neither provider succeeds. It never enables account billing.
This integration is web search; it does not claim LinkedIn authenticated
access, video viewing, or YouTube transcript extraction.

Every accepted search result retains its original source URL, title, text,
retrieval date and qualified confidence. Missing sources and provider errors
remain explicit gaps. Free remote access can be rate-limited or changed by
the provider; package installation is not proof of live availability.

Contact enrichment now reaches both the writer and reviewer. Directory
presence remains distinct from proof that a company imports the product.
Failed mission status is preserved. The pipeline and report regeneration
both use this handoff.

Related regression fixes retain Arabic metric identity despite diacritics,
accept only source-backed decimal display rounding at the stated precision,
and use the gosom web API's numeric timeout, language, capitalized status and
CSV download contract. Reviewer instructions distinguish direct and mirror
data and prohibit unsupported pilot quantities or maximum-loss claims.

Offline checks: `test_agent_reach_search.py`, `test_writer_handoff.py`,
`test_scraper_web_contract.py`, `test_pillar_arabic_metric_identity.py`,
`test_evidence_display_rounding.py`, `test_search_credit_diagnosis.py`.
