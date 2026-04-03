"""Slack notification module for the CFIC scraper.

Sends formatted messages to a Slack channel when new events are found.
"""

import logging

import requests

from .config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID
from .scraper import CficEvent

logger = logging.getLogger(__name__)

SLACK_POST_URL = "https://slack.com/api/chat.postMessage"


def _build_event_blocks(event: CficEvent) -> list[dict]:
    """Build Slack Block Kit blocks for an event notification."""
    blocks: list[dict] = []

    # Header
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"New CFIC Event: {event.title}",
                "emoji": True,
            },
        }
    )

    # Core details section
    fields = []
    if event.date:
        fields.append({"type": "mrkdwn", "text": f"*Date:*\n{event.date}"})
    if event.event_type:
        fields.append({"type": "mrkdwn", "text": f"*Type:*\n{event.event_type}"})
    if event.location:
        fields.append({"type": "mrkdwn", "text": f"*Location:*\n{event.location}"})
    if event.eligibility:
        fields.append({"type": "mrkdwn", "text": f"*Eligibility:*\n{event.eligibility}"})

    if fields:
        blocks.append({"type": "section", "fields": fields})

    # Purpose
    if event.purpose:
        purpose_text = event.purpose
        if len(purpose_text) > 2900:
            purpose_text = purpose_text[:2900] + "..."
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Purpose:*\n{purpose_text}",
                },
            }
        )

    # RSVP deadline
    if event.rsvp_deadline:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*RSVP Deadline:*\n{event.rsvp_deadline}",
                },
            }
        )

    # Speaker info (for webinars)
    if event.speaker_name:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Speaker:*\n{event.speaker_name}",
                },
            }
        )

    # Key takeaways
    if event.key_takeaways:
        takeaways = "\n".join(f"- {t}" for t in event.key_takeaways)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Key Takeaways:*\n{takeaways}",
                },
            }
        )

    # Contact info
    if event.tpoc_name or event.tpoc_email:
        contact_parts = []
        if event.tpoc_name:
            contact_parts.append(event.tpoc_name)
        if event.tpoc_email:
            contact_parts.append(event.tpoc_email)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Contact:*\n{' | '.join(contact_parts)}",
                },
            }
        )

    # Divider
    blocks.append({"type": "divider"})

    # Action buttons
    button_elements = []
    if event.detail_url:
        button_elements.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Event Details"},
                "url": event.detail_url,
                "style": "primary",
            }
        )
    if event.rsvp_url:
        button_elements.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "RSVP Now"},
                "url": event.rsvp_url,
            }
        )
    if event.pdf_download_url:
        button_elements.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Download Release"},
                "url": event.pdf_download_url,
            }
        )

    if button_elements:
        blocks.append({"type": "actions", "elements": button_elements})

    return blocks


def send_event_notification(event: CficEvent) -> bool:
    """Send a Slack notification for a single new event.

    Returns True if the message was sent successfully.
    """
    blocks = _build_event_blocks(event)
    fallback_text = f"New CFIC Event: {event.title} - {event.date}"

    payload = {
        "channel": SLACK_CHANNEL_ID,
        "text": fallback_text,
        "blocks": blocks,
    }

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    response = requests.post(SLACK_POST_URL, json=payload, headers=headers, timeout=15)
    response.raise_for_status()
    result = response.json()

    if result.get("ok"):
        logger.info("Slack notification sent for: %s", event.title)
        return True

    logger.error(
        "Slack API error for '%s': %s",
        event.title,
        result.get("error", "unknown"),
    )
    return False


def notify_new_events(events: list[CficEvent]) -> int:
    """Send Slack notifications for a list of new events.

    Returns the number of successfully sent notifications.
    """
    if not events:
        logger.info("No new events to notify about")
        return 0

    success_count = 0
    for event in events:
        try:
            if send_event_notification(event):
                success_count += 1
        except Exception:
            logger.exception("Failed to send Slack notification for: %s", event.title)

    logger.info(
        "Sent %d/%d Slack notifications", success_count, len(events)
    )
    return success_count
