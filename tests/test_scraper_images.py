from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from scraping.scraper import build_listing_from_raw, normalize_listing_image_url  # noqa: E402


def test_normalize_listing_image_url_accepts_srcset_values():
    assert (
        normalize_listing_image_url(
            "//img4.idealista.com/blur/480_360_mq/0/id.pro.es.image.master/example.jpg 1x, "
            "//img4.idealista.com/blur/720_540_mq/0/id.pro.es.image.master/example.jpg 2x"
        )
        == "https://img4.idealista.com/blur/480_360_mq/0/id.pro.es.image.master/example.jpg"
    )


def test_build_listing_from_raw_normalizes_relative_image_url():
    listing = build_listing_from_raw(
        {
            "url": "/inmueble/123/",
            "price": "250.000 €",
            "details": ["80 m²", "3 hab."],
            "title": "Piso en venta",
            "image": "/static/common/img/example.jpg",
        },
        source_stage="same_street",
    )

    assert listing is not None
    assert listing.image_url == "https://www.idealista.com/static/common/img/example.jpg"
