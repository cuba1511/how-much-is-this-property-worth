"""Coverage check — does a geocoded municipio fall in the Alicante MVP?

Kept intentionally tiny and self-contained. The production `/api/valuation`
endpoint does NOT use this — it always goes through the Idealista scraper.
Only the `/api/valuation/alicante` endpoint reads it to decide whether to
snap the address into the Alicante centroid or proceed with the geocoded
location.

Post-MVP this will likely move into a per-province config table; for now a
hardcoded frozenset is enough.
"""
from __future__ import annotations

import logging
from typing import Optional

from models import MunicipioInfo

from alicante import storage

logger = logging.getLogger(__name__)


# Slugs (from `geocoding.geocoder.slugify`) that should use the local dataset.
# The Alicante export only contains the Alicante/Alacant municipio (admin3),
# so we keep the set minimal. Aliases are normalized at slug level.
COVERAGE_SLUGS: frozenset[str] = frozenset(
    {
        "alicante-alacant",
        "alicante",
        "alacant",
    }
)


def municipio_in_coverage(municipio: Optional[MunicipioInfo]) -> bool:
    """True when the municipio is in the Alicante MVP coverage and the
    local dataset is loaded. False otherwise (route caller decides what to do)."""
    if municipio is None:
        return False
    slug = (municipio.slug or "").strip().lower()
    if slug not in COVERAGE_SLUGS:
        return False
    try:
        return storage.listings_count() > 0
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Coverage check failed: %s", exc)
        return False


__all__ = ["COVERAGE_SLUGS", "municipio_in_coverage"]
