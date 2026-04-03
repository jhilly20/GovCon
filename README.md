# Government Opportunity Scrapers

A collection of Python scrapers for monitoring government procurement and research opportunities from various federal agencies.

## 🚀 Features

- **Multi-platform Support**: Scrapes opportunities from SAM.gov (custom searches), Challenge.gov, SDA, and CyberFIC
- **Slack Integration**: Get notifications in Slack when new opportunities are posted
- **Monday.com Integration**: Automatically create items in Monday.com boards for tracking
- **Environment-based Configuration**: Secure API key management
- **Customizable Searches**: Easy to modify search parameters for specific needs

## 📋 Available Scrapers

| Scraper | Agency | Description |
|---------|--------|-------------|
| `custom_samgov_search.py` | SAM.gov | Custom SAM.gov search example (formerly Cognition) |
| `small_biz_samgov_search.py` | SAM.gov | NAICS 541715 small business set-aside opportunities |
| `industry_day_scraper.py` | SAM.gov | Industry Day events and conferences |
| `challenge_gov_scraper.py` | Challenge.gov | Federal challenge competitions and prizes |
| `sda_scraper.py` | SDA | Space Development Agency opportunities |
| `cfic/` | CFIC / ARCYBER | CyberFIC collaboration events, webinars, and assessments |

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

# Slack (optional - for notifications)
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token-here
SLACK_CHANNEL=your_slack_channel_id_here

# SAM.gov (required for SAM.gov scraper)
SAM_API_KEY=your_sam_api_key_here
```

### Getting API Keys

- **Monday.com**: Visit https://developer.monday.com/api/docs/authentication
- **Slack**: Create a bot app at https://api.slack.com/apps
- **SAM.gov**: Request an API key at https://sam.gov/api/key-request

## 🎯 Usage

### Command Line Usage

```bash
# Run individual scrapers
python scrapers/custom_samgov_search.py      # Custom SAM.gov search
python scrapers/small_biz_samgov_search.py   # Small business set-asides
python scrapers/industry_day_scraper.py      # Industry Day events
python scrapers/challenge_gov_scraper.py     # Challenge competitions
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
- **Search term**: "Industry Day" 
- **Notice type**: Special notices (type "s")
- **Event dashboard**: Creates items in a dedicated Monday.com board

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

## 📝 Notes

- These scrapers are provided for educational and research purposes
- Always respect website terms of service and rate limits
- Some sites may require additional authentication or have anti-scraping measures
- Consider adding delays between requests to avoid overwhelming servers

## ⚠️ Disclaimer

This software is not affiliated with any government agency. Users are responsible for ensuring compliance with all applicable laws and terms of service.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [Requests](https://requests.readthedocs.io/) and [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- Inspired by the need to streamline opportunity discovery for researchers and businesses
