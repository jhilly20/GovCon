# Testing GovCon Scrapers

## Overview
This repo contains 6+ government opportunity scrapers that fetch data from various sources (SAM.gov, CyberFIC.org, Challenge.gov, SDA) and sync results to a Monday.com board with Slack notifications.

## Devin Secrets Needed
- `MONDAY_API_KEY` — Monday.com API token (JWT format, starts with `eyJ`)
- `MONDAY_BOARD_ID` — Monday.com board ID (numeric string)
- `SLACK_BOT_TOKEN` — Slack bot token (starts with `xoxb-`)
- `SLACK_CHANNEL` — Slack channel ID (e.g. `C09P0R097NF`)
- `CUAS_SLACK_CHANNEL` — Optional, CUAS-specific Slack channel
- `SAM_API_KEY` — Optional, SAM.gov API key (scrapers work without it using the public search endpoint)

## Environment Setup
1. Create `.env` in repo root with the secrets above (copy from `.env.example`)
2. Install dependencies: `pip install -r requirements.txt`
3. All scrapers use `python-dotenv` to load from the repo root `.env` file

## Running Scrapers

### CFIC Scraper (CyberFIC.org)
```bash
python -m scrapers.cfic.main
```
- Scrapes upcoming events from cyberfic.org/events
- No API key needed for scraping (just HTTP requests to the website)
- Syncs to Monday.com and sends Slack notifications for new events
- Typically finds 2-3 upcoming events

### Industry Day Scraper (SAM.gov)
```bash
python scrapers/industry_day_scraper.py
```
- Searches SAM.gov for Industry Day events
- **Does NOT require SAM_API_KEY** — uses the public search endpoint
- Can return 100+ results; each triggers a detail API call + Monday.com create
- May take 2+ minutes for large result sets
- Use `timeout 120` prefix if you need to cap execution time

### Small Biz SAM.gov Scraper
```bash
python scrapers/small_biz_samgov_search.py
```
- Searches NAICS 541715 small business set-asides
- Does NOT require SAM_API_KEY
- Uses `monday_find_item_by_topic()` for deduplication before creating items

### Custom SAM.gov Search
```bash
python scrapers/custom_samgov_search.py
```
- Custom keyword search (COBOL, FORTRAN, DevSecOps, etc.)
- Same SAM.gov pattern as above

### Challenge.gov Scraper
```bash
python scrapers/challenge_gov_scraper.py
```
- **Known issue:** The Challenge.gov API endpoint (`portal.challenge.gov/api/challenges`) may return HTML instead of JSON. This might be a temporary issue or the API may have changed. The scraper handles this gracefully (logs error, returns empty list).

### SDA Scraper
```bash
cd scrapers && python sda_scraper.py
```
- Must be run from the `scrapers/` directory (or with `scrapers/` on PYTHONPATH) since it imports `base_scraper`
- Inherits from `BaseScraper` class

## Testing Strategy

### Unit Tests (no live API calls)
1. **dotenv loading**: Import each module with env vars cleared, verify they load from `.env`
2. **Edge cases**: Test quoted values, `=` in values, inline comments in `.env`
3. **Guard conditions**: Verify `if tpoc_email else None` guards produce correct output for empty/non-empty inputs
4. **Source code inspection**: Use `inspect.getsource()` to verify guards exist in actual code

### End-to-End Tests (live API calls)
1. Run each scraper and verify:
   - No Python tracebacks or exceptions
   - Monday.com items are created successfully (look for `create_item` responses)
   - Slack notifications are sent (HTTP 200)
   - Deduplication works (existing items are skipped)
2. Check output with `grep -i 'error\|fail\|traceback\|exception'`

### Important Notes
- Running scrapers against live APIs **will create real items** on the Monday.com board. Subsequent runs will deduplicate, but the first run adds items.
- SAM.gov public endpoints have no rate limiting observed, but be respectful with large queries.
- The Slack bot must be invited to the target channel first (`/invite @botname`).
- All testing is shell-based (no browser/GUI needed). Do NOT record screen for testing.
