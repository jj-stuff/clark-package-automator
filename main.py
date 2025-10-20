import email
import imaplib
import logging
import os
from dataclasses import dataclass
from email.message import Message
from typing import Optional

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Configure structured logging once at import-time for both CLI usage and CI.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    """Container for all runtime configuration values."""

    imap_server: str
    email_address: str
    email_password: str
    sender_address: str
    form_url: str
    first_name: str
    last_name: str
    room_number: str

    @property
    def user_info(self) -> dict[str, str]:
        """Structure the user metadata payload expected by the form."""
        return {
            "FIRST_NAME": self.first_name,
            "LAST_NAME": self.last_name,
            "ROOM_NUMBER": self.room_number,
        }


def load_config() -> Config:
    """
    Load settings from the environment (or .env when running locally).

    Raises:
        ValueError: if any required environment variable is missing.
    """
    load_dotenv()

    env_map = {
        "imap_server": os.getenv("IMAP_SERVER"),
        "email_address": os.getenv("EMAIL_ADDRESS"),
        "email_password": os.getenv("EMAIL_APP_PASSWORD"),
        "sender_address": os.getenv("SENDER_ADDRESS"),
        "form_url": os.getenv("FORM_URL"),
        "first_name": os.getenv("FIRST_NAME"),
        "last_name": os.getenv("LAST_NAME"),
        "room_number": os.getenv("ROOM_NUMBER"),
    }

    missing = [name for name, value in env_map.items() if not value]
    if missing:
        raise ValueError(
            "Missing required configuration values: "
            + ", ".join(sorted(missing))
        )

    return Config(
        imap_server=env_map["imap_server"],
        email_address=env_map["email_address"],
        email_password=env_map["email_password"],
        sender_address=env_map["sender_address"],
        form_url=env_map["form_url"],
        first_name=env_map["first_name"],
        last_name=env_map["last_name"],
        room_number=env_map["room_number"],
    )


def connect_mailbox(config: Config) -> imaplib.IMAP4_SSL:
    """Create an IMAP SSL connection to the configured inbox."""
    LOGGER.info("Connecting to IMAP server %s as %s", config.imap_server, config.email_address)
    mail = imaplib.IMAP4_SSL(config.imap_server)
    mail.login(config.email_address, config.email_password)
    # Selecting INBOX in read/write mode allows us to mark messages as seen after processing.
    mail.select("INBOX")
    return mail


def fetch_unread_messages(mail: imaplib.IMAP4_SSL, sender_address: str) -> list[bytes]:
    """
    Retrieve the list of unread message IDs from the specified sender.

    Returns:
        A list of message IDs (as bytes) representing unread emails.
    """
    status, data = mail.search(None, "UNSEEN", f'FROM "{sender_address}"')

    if status != "OK":
        raise RuntimeError("Unable to search for unread emails.")

    # The IMAP response is a single space separated string of IDs.
    message_ids = data[0].split()
    LOGGER.info("Found %d unread message(s) from %s", len(message_ids), sender_address)
    return message_ids


def get_message(mail: imaplib.IMAP4_SSL, message_id: bytes) -> Optional[Message]:
    """
    Fetch the full message without altering read status.

    Returns:
        Parsed email Message if the fetch succeeds, otherwise None.
    """
    status, payload = mail.fetch(message_id, "(BODY.PEEK[])")
    if status != "OK" or not payload:
        LOGGER.warning("Unable to fetch message id %s", message_id.decode(errors="ignore"))
        return None

    raw_message = payload[0][1]
    return email.message_from_bytes(raw_message)


def extract_html_body(message: Message) -> Optional[str]:
    """Return the HTML part of the email if present."""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/html":
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
                except (LookupError, UnicodeDecodeError):
                    return part.get_payload(decode=True).decode("utf-8", errors="replace")
    else:
        if message.get_content_type() == "text/html":
            try:
                return message.get_payload(decode=True).decode(message.get_content_charset() or "utf-8")
            except (LookupError, UnicodeDecodeError):
                return message.get_payload(decode=True).decode("utf-8", errors="replace")
    return None


def parse_package_info(email_html: str) -> Optional[dict[str, str]]:
    """Parse the HTML body to extract the tracking number."""
    soup = BeautifulSoup(email_html, "lxml")
    tracking_tag = soup.find(
        "strong", string=lambda text: text and "TRACKING NO:" in text.upper()
    )

    if not tracking_tag:
        return None

    tracking_sibling = tracking_tag.next_sibling
    tracking_number = str(tracking_sibling).strip() if tracking_sibling else ""
    if not tracking_number:
        return None

    return {"tracking_id": tracking_number}


def submit_package_form(url: str, package_info: dict[str, str], user_info: dict[str, str]) -> None:
    """Automate the cognito form submission for the provided package."""
    tracking_id = package_info["tracking_id"]
    LOGGER.info("Submitting form for tracking number %s", tracking_id)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()

        # Wait until the network is idle to ensure the form is fully loaded.
        page.goto(url, wait_until="networkidle")

        page.locator('[placeholder="First"]').fill(user_info["FIRST_NAME"])
        page.locator('[placeholder="Last"]').fill(user_info["LAST_NAME"])
        page.get_by_label("Room Number").fill(user_info["ROOM_NUMBER"])
        page.get_by_label("Tracking No").fill(tracking_id)

        page.get_by_role("button", name="Submit").click()

        # Wait for the submission to finish and capture a screenshot for auditing.
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"submission_{tracking_id}.png")
        browser.close()

    LOGGER.info("Form submitted for tracking number %s", tracking_id)


def check_for_new_packages() -> None:
    """Top-level orchestration for locating unread package emails and filing them."""
    try:
        config = load_config()
    except ValueError as error:
        LOGGER.error("%s", error)
        return

    try:
        mail = connect_mailbox(config)
    except imaplib.IMAP4.error as error:
        LOGGER.error("Failed to authenticate with IMAP server: %s", error)
        return
    except OSError as error:
        LOGGER.error("Unable to connect to IMAP server: %s", error)
        return

    try:
        message_ids = fetch_unread_messages(mail, config.sender_address)
        if not message_ids:
            LOGGER.info("No unread package notifications found.")
            return

        for message_id in message_ids:
            message = get_message(mail, message_id)
            if not message:
                continue

            html_body = extract_html_body(message)
            if not html_body:
                LOGGER.warning("Email %s does not contain HTML content.", message_id.decode(errors="ignore"))
                continue

            package_info = parse_package_info(html_body)
            if not package_info:
                LOGGER.warning(
                    "Could not locate a tracking number in email %s.",
                    message_id.decode(errors="ignore"),
                )
                continue

            try:
                submit_package_form(config.form_url, package_info, config.user_info)
            except Exception as error:
                LOGGER.exception("Form submission failed for %s: %s", package_info["tracking_id"], error)
                continue

            # Mark the message as seen only after a successful submission.
            mail.store(message_id, "+FLAGS", "\\Seen")

    finally:
        try:
            mail.close()
        except Exception:  # best-effort close if the mailbox was never opened
            pass
        mail.logout()


if __name__ == "__main__":
    check_for_new_packages()
