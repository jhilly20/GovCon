# CFIC Event Scraper

Scrapes upcoming events from [CyberFIC.org](https://www.cyberfic.org/events), syncs them to a Monday.com board, and sends Slack notifications when new events are discovered.

## Setup

### 1. Install dependencies

```bash
pip install -r scrapers/cfic/requirements.txt
```

### 2. Configure environment variables

Copy the example file and fill in your credentials:

```bash
cp scrapers/cfic/.env.example .env
```

| Variable | Description |
|----------|-------------|
| `MONDAY_API_TOKEN` | Monday.com API token ([generate here](https://monday.com/apps/manage)) |
| `MONDAY_BOARD_ID` | ID of the Monday.com board to sync events to |
| `SLACK_BOT_TOKEN` | Slack bot token (starts with `xoxb-`) |
| `SLACK_CHANNEL_ID` | Slack channel ID to post notifications to |

### 3. Run the scraper

```bash
python -m scrapers.cfic
```

## How It Works

1. **Scrape**: Fetches the CyberFIC events page and identifies upcoming events. Follows each event's "Learn More" link to collect detailed information (purpose, background, RSVP deadlines, contacts, etc.)

2. **Sync to Monday.com**: Compares scraped events against existing items on the board. Only creates new items for events that don't already exist (matched by title).

3. **Slack Notification**: Sends a formatted message to Slack for each newly added event, including event details, RSVP links, and downloadable resources.

## Monday.com Column Mapping

| Field | Column ID | Description |
|-------|-----------|-------------|
| Item Name | `name` | Event title |
| Close Date | `date_mkkqedzc` | Event date |
| Link | `text_mkkq2vab` | URL to event detail page |
| Description | `text_mkkqeet2` | Purpose, background, and key details |
| TPOC | `text_mkkqftmh` | Technical Point of Contact name |
| TPOC Email | `tpoc_email_mkmfdxba` | Contact email |
| TPOC Phone | `tpoc_phone_mkmfav28` | Contact phone |
| Agency | `text_mkvqfmz5` | Issuing agency (defaults to "CFIC / ARCYBER") |
| Source | `text_mktm7tsx` | Scraper identifier ("CFIC Scraper") |

## Scheduling

To run the scraper on a schedule (e.g., daily), set up a cron job or GitHub Actions workflow:

```bash
# Example cron: run daily at 8 AM ET
0 12 * * * cd /path/to/GovCon && python -m scrapers.cfic
```

## Event Types Detected

- **Collaboration Event (CE)** — in-person events with purpose/synopsis, RSVP deadlines, PDF releases
- **Assessment Event (AE)** — targeted problem events with desirements
- **Connector Series Webinar** — virtual speaker series with key takeaways
- **Q & A Session** — pre-submission Q&A with ARCYBER stakeholders
