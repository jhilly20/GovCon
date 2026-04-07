# Government Opportunity Scrapers

A collection of Python scrapers for monitoring government procurement and research opportunities from various federal agencies. All scrapers integrate with Monday.com for tracking and Slack for notifications.

## 🚀 Features

- **20+ scrapers** covering SAM.gov, SBIR/STTR, OTA consortia, DARPA, DIU, DHS, and more
- **BaseScraper pattern**: New scrapers inherit from `BaseScraper` for consistent Monday.com/Slack integration and deduplication
- **Slack Integration**: Automatic notifications when new opportunities are found
- **Monday.com Integration**: Auto-create items in Monday.com boards (opportunities board + event dashboard)
- **Environment-based Configuration**: Secure API key management via `.env`
- **Selenium support**: Headless browser scraping for JS-heavy and login-required sites

## 📋 Available Scrapers

### Opportunity Scrapers (BaseScraper pattern)

These scrapers inherit from `BaseScraper` and post to the main opportunities Monday.com board.

| Scraper | Source | Method | Verified | Notes |
|---------|--------|--------|----------|-------|
| `dod_sbirsttr_scraper.py` | [DoD SBIR/STTR](https://www.dodsbirsttr.mil) | REST API | Yes | Public API, fetches open/pre-release topics |
| `darpa_scraper.py` | [DARPA](https://www.darpa.mil/work-with-us/opportunities) | RSS feed | Yes | Parses RSS, extracts deadlines from descriptions |
| `erdcwerx_scraper.py` | [ERDCWERX](https://www.erdcwerx.org) | WordPress API + HTML | Yes | WP REST API for listing, HTML scraping for deadlines |
| `diu_scraper.py` | [DIU](https://www.diu.mil/work-with-us/open-solicitations) | HTML (Nuxt SSR) | Yes | Server-rendered, no JS needed |
| `grantsgov_scraper.py` | [Grants.gov](https://simpler.grants.gov) | REST API | Yes | Filters by for-profit/small-biz eligibility codes |
| `colosseum_scraper.py` | [Colosseum (ONI)](https://marketplace.gocolosseum.org) | HTML | Yes | Public homepage, no login needed |
| `challenge_gov_scraper.py` | [USA.gov Challenges](https://www.usa.gov/find-active-challenge) | HTML | Yes | Detail page enrichment with deadlines, prizes, agencies |
| `dhs_sbir_scraper.py` | [DHS SBIR](https://oip.dhs.gov/sbir/public) | Selenium | No | Cloudflare-protected; falls back to sbir.gov |
| `tradewind_scraper.py` | [Tradewind AI](https://www.tradewindai.com/opportunities) | Selenium | No | Wix site, CSS selectors need live validation |
| `vulcan_sof_scraper.py` | [Vulcan SOF](https://vulcan-sof.com) | Selenium (visible) | No | Requires login + 2FA; runs non-headless for manual 2FA entry |

### SAM.gov Scrapers (standalone)

These scrapers predate BaseScraper and have their own Monday.com/Slack integration.

| Scraper | Source | Description |
|---------|--------|-------------|
| `custom_samgov_search.py` | SAM.gov | Custom SAM.gov search template |
| `small_biz_samgov_search.py` | SAM.gov | NAICS 541715 small business set-aside opportunities |
| `industry_day_scraper.py` | SAM.gov | Industry Day events -- posts to Event Dashboard board |

### Event / Other Scrapers

| Scraper | Source | Description |
|---------|--------|-------------|
| `sda_scraper.py` | SDA | Space Development Agency opportunities |
| `cfic/` | CFIC / ARCYBER | CyberFIC collaboration events, webinars, and assessments |

> **Note:** Not all scrapers have been verified end-to-end with live Monday.com/Slack integration. The "Verified" column above indicates whether the scraper has been tested against the live source and confirmed to fetch/parse data correctly. Selenium-based scrapers in particular need live validation of CSS selectors, which may change when sites update their layouts.

## 🛠️ Installation

1. Clone this repository:
```bash
git clone https://github.com/jhilly20/GovCon.git
cd GovCon
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

## ⚙️ Configuration

Create a `.env` file based on `.env.example`:

### Required Environment Variables

```bash
# Monday.com (optional - for tracking opportunities)
MONDAY_API_KEY=your_monday_api_key_here
MONDAY_BOARD_ID=your_board_id_here
MONDAY_EVENT_BOARD_ID=your_event_board_id_here  # Event Dashboard board (industry days)

# Slack (optional - for notifications)
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token-here
SLACK_CHANNEL=your_slack_channel_id_here

# SAM.gov (optional - search works without it)
SAM_API_KEY=your_sam_api_key_here

# Vulcan SOF (required for vulcan_sof_scraper only)
VULCAN_SOF_EMAIL=your_email_here
VULCAN_SOF_PASSWORD=your_password_here

# Colosseum credentials (if login required)
COLOSSEUM_EMAIL=your_email_here
COLOSSEUM_PASSWORD=your_password_here
```

### Getting API Keys

- **Monday.com**: Visit https://developer.monday.com/api/docs/authentication
- **Slack**: Create a bot app at https://api.slack.com/apps
- **SAM.gov**: Request an API key at https://sam.gov/api/key-request
- **Grants.gov**: No key needed (public `search2` API)

## 🎯 Usage

### Command Line Usage

```bash
# SAM.gov scrapers
python scrapers/custom_samgov_search.py      # Custom SAM.gov search
python scrapers/small_biz_samgov_search.py   # Small business set-asides
python scrapers/industry_day_scraper.py      # Industry Day events (Event Dashboard)

# BaseScraper-based opportunity scrapers
python scrapers/dod_sbirsttr_scraper.py      # DoD SBIR/STTR topics
python scrapers/darpa_scraper.py             # DARPA opportunities (RSS)
python scrapers/erdcwerx_scraper.py          # ERDCWERX tech challenges
python scrapers/diu_scraper.py               # DIU open solicitations
python scrapers/grantsgov_scraper.py         # Grants.gov (for-profit eligible)
python scrapers/colosseum_scraper.py         # Colosseum / ONI challenges
python scrapers/challenge_gov_scraper.py     # USA.gov challenge competitions

# Selenium-based scrapers (require browser)
python scrapers/dhs_sbir_scraper.py          # DHS SBIR (Cloudflare)
python scrapers/tradewind_scraper.py         # Tradewind AI (Wix)
python scrapers/vulcan_sof_scraper.py        # Vulcan SOF (login + 2FA)

# Other
python scrapers/sda_scraper.py               # Space Development Agency
python -m scrapers.cfic                      # CyberFIC events
```

## 🔧 Customization

### Custom SAM.gov Search

The `custom_samgov_search.py` file shows how to create targeted searches. Key parameters to modify:

```python
# Example search parameters
params = {
    "q": "your search terms here",
    "naics": "541715",  # NAICS code for your industry
    "set_aside": "SBP,SBA",  # Small business set-asides
    "notice_type": "p"  # Presolicitations only
}
```

### Small Business Set-Aside Search

The `small_biz_samgov_search.py` is specifically configured for:
- **NAICS 541715**: Computer Systems Design Services
- **Set-asides**: Small Business (SBP) and SBA programs
- **Custom Slack labeling**: "small biz setaside 541715 sam.gov"

### Industry Day Events

The `industry_day_scraper.py` searches for:
- **Industry Day events**: Government-hosted industry days and conferences
- **Search term**: "Industry Day" on SAM.gov
- **Notice type**: Special notices (type "s")
- **Event Dashboard board**: Posts to `MONDAY_EVENT_BOARD_ID` (separate from the opportunities board)
- **Deduplication**: By solicitation number to prevent recreating existing items
- **Detail enrichment**: Fetches v2 detail endpoint for authoritative links and topic numbers

### CyberFIC Events

The `cfic/` package scrapes upcoming events from [CyberFIC.org](https://www.cyberfic.org/events):
- **Collaboration Events (CE)**: In-person events with purpose/synopsis, RSVP deadlines, PDF releases
- **Assessment Events (AE)**: Targeted problem events with desirements
- **Connector Series Webinars**: Virtual speaker series with key takeaways
- **Q & A Sessions**: Pre-submission Q&A with ARCYBER stakeholders
- Automatically follows detail page links to collect full event information
- Syncs to Monday.com and sends Slack notifications for new events

### Custom Monday.com Integration

If you want to use Monday.com, update the column mappings in each scraper's config section:

```python
# Monday.com column mappings
TITLE_COLUMN = "your_title_column_id"
DESCRIPTION_COLUMN = "your_description_column_id"
URL_COLUMN = "your_url_column_id"
DEADLINE_COLUMN = "your_deadline_column_id"
AGENCY_COLUMN = "your_agency_column_id"
```

## 📊 Output

Each scraper returns a list of opportunity dictionaries with the following structure:

```python
{
    "title": "Opportunity Title",
    "description": "Full description",
    "url": "Direct link to opportunity",
    "deadline": "YYYY-MM-DD",
    "agency": "Agency Name",
    "posted_date": "YYYY-MM-DD"
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-scraper`
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📅 Planned / In Progress

The following scrapers and integrations are planned for future development:

### Upcoming Scrapers (Medium Priority)

| Source | Status | Notes |
|--------|--------|-------|
| [MITRE AiDA OTA Consortia](https://aida.mitre.org/ota/existing-ota-consortia/) | In progress | Per-consortium opportunity parsing; prepend consortium name to titles |
| [CyberFIC](https://www.cyberfic.org/events) | Done | Already implemented in `cfic/` |
| [ICWERX](https://www.icwerx.org/opportunities) | Planned | |
| [NASA SBIR/STTR](https://www.nasa.gov/sbir_sttr/) | Planned | |
| [DOE SBIR](https://science.osti.gov/sbir/Funding-Opportunities/FY-2026) | Planned | |
| [ConnectWERX](https://www.connectwerx.org/opportunities/) | Planned | |
| [EnergyWERX](https://www.energywerx.org/opportunities) | Planned | |
| [HSWERX](https://www.hswerx.org/events) | Planned | |

### Upcoming Scrapers (Low Priority)

| Source | Status | Notes |
|--------|--------|-------|
| [NAM Consortium](https://www.namconsortium.org/opportunities) | Planned | |
| [TechConnect](https://techconnect.org/opportunities/) | Planned | WordPress REST API available |
| [ARL DEVCOM](https://arl.devcom.army.mil/collaborate-with-us/avenue/funded-research/) | Planned | |
| [NSPIRES (NASA)](https://nspires.nasaprs.com/external/solicitations/solicitations!init.do) | Planned | |
| [ARPA-E](https://arpa-e-foa.energy.gov/Default.aspx) | Planned | |
| [EERE Exchange](https://eere-exchange.energy.gov/Default.aspx) | Planned | |
| [DOE PAMS](https://pamspublic.science.energy.gov/WebPAMSExternal/Interface/Proposal/Solicitation/FOAList.aspx) | Planned | |
| [DHS Forecast](https://apfs-cloud.dhs.gov/forecast/) | Planned | |
| [Volpe DOT SBIR](https://www.volpe.dot.gov/work-with-us/small-business-innovation-research/solicitations) | Planned | Cloudflare-protected |
| [ARPA-I](https://www.transportation.gov/arpa-i) | Planned | |
| [NIST SBIR](https://www.nist.gov/tpo/small-business-innovation-research-program-sbir) | Planned | |
| [NOAA SBIR](https://techpartnerships.noaa.gov/sbir/fundingopportunities/) | Planned | |

### Calendar Integrations (Lower Priority)

Future integration with event calendars for automatic syncing:
- Google Calendar (DEF.org events, imported calendars)
- [CTO Innovation events](https://www.ctoinnovation.mil/events)
- [NCSI calendar](https://www.ncsi.com/calendar/)

## 📝 Notes

- These scrapers are provided for educational and research purposes
- Always respect website terms of service and rate limits
- Some sites may require additional authentication or have anti-scraping measures
- Consider adding delays between requests to avoid overwhelming servers
- **Not all scrapers have been verified end-to-end yet.** API-based scrapers (DoD SBIR, DARPA, ERDCWERX, DIU, Grants.gov, Colosseum) have been tested against live sources. Selenium-based scrapers (DHS SBIR, Tradewind, Vulcan SOF) need live validation of CSS selectors.

## ⚠️ Disclaimer

This software is not affiliated with any government agency. Users are responsible for ensuring compliance with all applicable laws and terms of service.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [Requests](https://requests.readthedocs.io/), [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/), and [Selenium](https://www.selenium.dev/)
- Inspired by the need to streamline opportunity discovery for researchers and small businesses
