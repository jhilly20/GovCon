# Testing GovCon Scrapers

## Running Scrapers Locally

All BaseScraper-derived scrapers support `--dry-run` mode which fetches data but skips Monday.com and Slack integration:

```bash
cd scrapers && python3 <scraper_name>.py --dry-run
```

If `MONDAY_API_KEY` is not set, scrapers automatically skip Monday.com/Slack even without `--dry-run`.

## Scraper Categories

### Phase 1 (API/RSS/Selenium)
- **No auth needed:** `dod_sbirsttr_scraper.py`, `darpa_scraper.py`, `erdcwerx_scraper.py`, `grantsgov_scraper.py`, `diu_scraper.py`, `industry_day_scraper.py`
- **Selenium, no auth:** `tradewind_scraper.py`, `colosseum_scraper.py`, `dhs_sbir_scraper.py`
- **Selenium + credentials:** `vulcan_sof_scraper.py` (needs `VULCAN_SOF_EMAIL`, `VULCAN_SOF_PASSWORD`, + 2FA)

### Phase 2 (HTML, no Selenium)
- `icwerx_scraper.py`, `connectwerx_scraper.py`, `energywerx_scraper.py`, `hswerx_scraper.py`
- `nam_scraper.py`, `nasa_sbir_scraper.py`, `doe_sbir_scraper.py`
- `nist_sbir_scraper.py`, `noaa_sbir_scraper.py`, `mitre_aida_scraper.py`

### Legacy (not BaseScraper)
- `challenge_gov_scraper.py`, `custom_samgov_search.py`, `small_biz_samgov_search.py`, `sda_scraper.py`

## Known Site Quirks

- **EnergyWERX**: Webflow site renders date parts in separate HTML elements. Deadline extraction joins block text before regex search.
- **NASA SBIR**: `sbir.gov/api/solicitations.json` returns 404. Scraper falls back to HTML page scraping.
- **MITRE AiDA**: Crawls 37+ consortium sites. Rate-limited with `time.sleep(0.5)` and capped at 15 sites per run. Takes ~30s.
- **ConnectWERX**: May return 0 items if all opportunities are currently closed (correct behavior).
- **NIST/NOAA SBIR**: Multiple items may share the same URL. Dedup uses `(URL, title)` tuple key.

## Environment Variables

- `MONDAY_API_KEY` — Required for Monday.com integration
- `MONDAY_BOARD_ID` — Target board for opportunities
- `MONDAY_EVENT_BOARD_ID` — Target board for `industry_day_scraper.py`
- `SLACK_BOT_TOKEN` / `SLACK_CHANNEL` — Slack notifications
- `SAM_API_KEY` — For SAM.gov scrapers
- `VULCAN_SOF_EMAIL` / `VULCAN_SOF_PASSWORD` — Vulcan SOF login

## Verification Checklist

When testing scrapers, verify:
1. Exit code 0 (no Python exceptions)
2. `Fetched N items` log line shows expected count
3. Items have populated `title` and `url` fields
4. Deadlines are extracted where the site provides them
5. Closed/past opportunities are filtered out
