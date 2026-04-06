# Testing GovCon Scrapers

## Overview
All scrapers extend `BaseScraper` in `scrapers/base_scraper.py` and follow the same pattern:
- `fetch_data()` — returns iterable of raw dicts from the source
- `extract_fields()` — transforms a raw dict into standardized fields: `title`, `description`, `url`, `deadline`, `agency`
- `run()` — orchestrates fetch → deduplicate → Monday.com upsert → Slack notification

## Testing Without Credentials (Dry Run)
Without `MONDAY_API_KEY`, `BaseScraper.run()` prints the first 5 items and skips Monday.com/Slack. You can also call `fetch_data()` and `extract_fields()` directly:

```python
from dod_sbirsttr_scraper import DoDSBIRSTTRScraper
scraper = DoDSBIRSTTRScraper()
items = list(scraper.fetch_data())
fields = scraper.extract_fields(items[0])
print(fields)  # Should have: title, description, url, deadline, agency
```

## Scraper Categories

### API-based (no credentials needed)
- `dod_sbirsttr_scraper.py` — REST API, requires `Referer: https://www.dodsbirsttr.mil/topics-app/` header
- `darpa_scraper.py` — RSS feed at `https://www.darpa.mil/rss/opportunities.xml`
- `erdcwerx_scraper.py` — WordPress REST API, category 6
- `grantsgov_scraper.py` — needs `GRANTS_GOV_API_KEY` for API mode, falls back to HTML

### HTML scraping (no credentials needed)
- `diu_scraper.py` — server-rendered Nuxt.js, may return 0 items if no open solicitations
- `mitre_aida_scraper.py` — follows 24+ consortium links, slow (~1.5s delay per site)

### Selenium headless (credentials or special handling needed)
- `tradewind_scraper.py` — Wix site, JS-rendered
- `vulcan_sof_scraper.py` — needs `VULCAN_SOF_EMAIL`, `VULCAN_SOF_PASSWORD`
- `colosseum_scraper.py` — needs `COLOSSEUM_EMAIL`, `COLOSSEUM_PASSWORD`
- `dhs_sbir_scraper.py` — Cloudflare-protected, has sbir.gov fallback

## Devin Secrets Needed
- `MONDAY_API_KEY` — for Monday.com upsert (all scrapers)
- `SLACK_BOT_TOKEN` — for Slack notifications (all scrapers)
- `MONDAY_BOARD_ID` — target board ID
- `SLACK_CHANNEL` — target Slack channel
- `VULCAN_SOF_EMAIL` / `VULCAN_SOF_PASSWORD` — Vulcan SOF login
- `COLOSSEUM_EMAIL` / `COLOSSEUM_PASSWORD` — Colosseum/ONI login
- `GRANTS_GOV_API_KEY` — Grants.gov Simpler API

## Validation Checklist
For each scraper, verify:
1. `fetch_data()` returns non-empty list (unless source genuinely has no open items)
2. `extract_fields()` returns all 5 required fields
3. `title` is non-empty and HTML-free
4. `url` points to a valid source page
5. `deadline` is in YYYY-MM-DD format when present
6. `agency` is set to a meaningful value

## Known Issues & Quirks
- **DoD SBIR/STTR API** requires `Referer` header or returns 403/500
- **MITRE AiDA WordPress fallback** may pick up non-opportunity content (team bios, events) from consortium sites that use WordPress. Category filtering per site would improve accuracy.
- **MITRE AiDA** takes 30-60+ seconds for a full run (24+ consortium sites with delays)
- **DHS SBIR** primary site (oip.dhs.gov) is Cloudflare-protected and will likely block headless Selenium
- **Tradewind AI** is a Wix site — content is mostly JS-rendered, HTML fallback has limited data
- **DIU** may return 0 items legitimately when no solicitations are open
- Selenium scrapers' CSS selectors were written from HTML analysis, not validated against live rendered DOM — they may need tuning

## Running All Scrapers
```bash
cd scrapers
# API-based (fast, no auth)
python3 dod_sbirsttr_scraper.py
python3 darpa_scraper.py
python3 erdcwerx_scraper.py
python3 diu_scraper.py

# Slow (follows many links)
python3 mitre_aida_scraper.py

# Selenium (needs chromedriver + possibly credentials)
python3 tradewind_scraper.py
python3 vulcan_sof_scraper.py
python3 colosseum_scraper.py
python3 dhs_sbir_scraper.py
python3 grantsgov_scraper.py
```
