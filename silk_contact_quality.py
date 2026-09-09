"""Conservative validation of collected contacts, including saved results."""
import re

_US_ADDRESS = re.compile(
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)\s+\d{5}(?:-\d{4})?\b")
_PLACEHOLDER_EMAILS = {"email@email.com", "user@domain.com", "name@domain.com",
                       "your@email.com", "yourname@email.com", "test@test.com"}


def clean_contact(lead, target_iso3=""):
    """Remove demonstrably foreign rows and placeholder email values; never guess."""
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
            domain in {"example.com", "example.org", "example.net"}):
        result["email"] = ""
    return result
