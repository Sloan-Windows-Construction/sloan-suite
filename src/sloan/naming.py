import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Tuple

DATE_FMT_DEFAULT = "%Y-%m-%d"

@dataclass
class NameParts:
    customer: str
    keyword_acr: str
    detail_acr: str
    date_str: str
    ext: str
    extra: str

class _SafeDict(dict):
    def __missing__(self, key):  # ignore unknown fields in template
        return ""

class Namer:
    def __init__(self, cfg: Dict):
        self.cfg = cfg

    @staticmethod
    def _lookup_acronym(items: List[Dict[str, str]], full: str) -> str:
        for it in items:
            if it.get("name") == full:
                return it.get("acronym", full)
        return full

    def keyword_acronym(self, keyword_full: str) -> str:
        return self._lookup_acronym(self.cfg.get("keywords", []), keyword_full)

    def brand_acronym(self, brand_full: str) -> str:
        return self._lookup_acronym(self.cfg.get("brands", []), brand_full)

    def location_acronym(self, side: str, loc_full: str) -> str:
        return self._lookup_acronym(self.cfg.get("locations", {}).get(side, []), loc_full)

    def render(
        self,
        customer: str,
        keyword_full: str,
        detail_full: str,
        is_brand: bool,
        date_override: Optional[str],
        ext: str,
        extra: str = "",
    ) -> Tuple[str, NameParts]:
        date_fmt = self.cfg.get("date_format", DATE_FMT_DEFAULT)
        date_str = date_override or datetime.now().strftime(date_fmt)
        keyword_acr = self.keyword_acronym(keyword_full)
        detail_acr = self.brand_acronym(detail_full) if is_brand else detail_full

        template = self.cfg.get("filename_template", "{customer} {keyword} {detail} {date}")

        # If no {extra} in template but user supplied extra, insert before {date} by default
        if extra and "{extra}" not in template:
            if "{date}" in template:
                template = template.replace("{date}", "{extra} {date}")
            else:
                template = template + " {extra}"

        fields = _SafeDict(
            customer=customer.strip(),
            keyword=keyword_acr,
            detail=(detail_acr or "").strip(),
            date=date_str,
            extra=(extra or "").strip(),
        )

        # Safe format (unknown placeholders → "")
        try:
            base = template.format_map(fields)
        except Exception:
            # absolute fallback—shouldn’t happen with SafeDict, but be defensive
            base = f"{fields['customer']} {fields['keyword']} {fields['detail']} {fields['extra']} {fields['date']}"

        # Collapse spaces, trim
        base = re.sub(r"\s+", " ", base).strip()

        return f"{base}{ext}", NameParts(fields["customer"], keyword_acr, detail_acr, date_str, ext, fields["extra"])
