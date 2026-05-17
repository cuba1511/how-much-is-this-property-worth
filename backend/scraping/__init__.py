"""Scraping layer — Idealista SERP collection + per-listing detail enrichment.

External dependencies: Bright Data Scraping Browser (CDP), Playwright.
"""

from scraping.scraper import scrape_idealista_listings

__all__ = ["scrape_idealista_listings"]
