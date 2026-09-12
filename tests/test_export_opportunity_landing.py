"""Static contracts for the public export opportunity acquisition path."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LandingOpportunityTests(unittest.TestCase):
    def test_landing_preview_is_branded_bilingual_and_value_free(self):
        html = (ROOT / 'web/platform-landing.html').read_text(encoding='utf-8')
        js = (ROOT / 'web/marketing.js').read_text(encoding='utf-8')
        self.assertIn('id="opportunityForm"', html)
        self.assertIn('src="/silk-logo.png"', html)
        self.assertIn('pattern="[0-9]{6}"', html)
        self.assertIn('سجّل لرؤية القيم بالدولار الأمريكي', html)
        self.assertIn('opTitle:', js)
        self.assertIn('/platform/export-opportunities/preview?hs_code=', js)
        self.assertIn('opportunity_hs=', js)
        self.assertNotIn('market.potential', js)

    def test_platform_restores_landing_product_intent(self):
        platform = (ROOT / 'web/platform.html').read_text(encoding='utf-8')
        opportunities = (ROOT / 'web/platform-opportunities.js').read_text(encoding='utf-8')
        self.assertIn('handleOpportunityReturn()', platform)
        self.assertIn('query.get("opportunity_hs")', platform)
        self.assertIn('openProduct(match.id)', platform)
        self.assertIn('async function openProduct(pid)', opportunities)


if __name__ == '__main__': unittest.main()

