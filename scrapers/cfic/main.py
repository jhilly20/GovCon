"""Main orchestrator for the CFIC event scraper.

Scrapes upcoming events from CyberFIC.org, syncs new events to Monday.com,
and sends Slack notifications for any newly discovered events.

Usage:
    python -m scrapers.cfic.main
"""

import logging
import sys

from .monday_client import sync_events
from .scraper import scrape_all_upcoming
from .slack_notifier import notify_new_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run() -> None:
    """Run the full scrape -> sync -> notify pipeline."""
    logger.info("Starting CFIC event scraper")

    # Step 1: Scrape upcoming events from CyberFIC.org
    logger.info("Step 1: Scraping upcoming events from CyberFIC.org...")
    events = scrape_all_upcoming()
    logger.info("Found %d upcoming events", len(events))

    if not events:
        logger.info("No upcoming events found. Exiting.")
        return

    for event in events:
        logger.info(
            "  - %s (%s) [%s]", event.title, event.date, event.event_type
        )

    # Step 2: Sync to Monday.com (creates items for new events only)
    logger.info("Step 2: Syncing events to Monday.com...")
    new_events = sync_events(events)

    if not new_events:
        logger.info("No new events to add. All events already exist on the board.")
        return

    logger.info("%d new event(s) added to Monday.com", len(new_events))

    # Step 3: Send Slack notifications for new events
    logger.info("Step 3: Sending Slack notifications for new events...")
    sent = notify_new_events(new_events)
    logger.info("Sent %d Slack notification(s)", sent)

    logger.info("CFIC scraper run complete.")


if __name__ == "__main__":
    run()
