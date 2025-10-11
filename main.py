import os
import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv


def check_for_new_packages():
    """
    @brief Connects to the email server, fetches unread package notifications,
           parses them, and submits them to the web form.
    """
    # Load environment variables from the .env file if running locally
    load_dotenv()

    # Load all settings from the environment variables
    imap_server = os.getenv("IMAP_SERVER")
    email_address = os.getenv("EMAIL_ADDRESS")
    # UPDATED: Use the more specific App Password variable name
    email_password = os.getenv("EMAIL_APP_PASSWORD")
    sender_address = os.getenv("SENDER_ADDRESS")
    form_url = os.getenv("FORM_URL")

    # Create a dictionary with user info for the form
    user_info = {
        "FIRST_NAME": os.getenv("FIRST_NAME"),
        "LAST_NAME": os.getenv("LAST_NAME"),
        "ROOM_NUMBER": os.getenv("ROOM_NUMBER"),
    }

    # Validate that all required environment variables are present
    if not all(
        [
            imap_server,
            email_address,
            email_password,
            sender_address,
            form_url,
            user_info["FIRST_NAME"],
        ]
    ):
        print(
            "Error: One or more required environment variables are missing. Check your secrets or .env file."
        )
        return

    print("Connecting to the email server...")
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, email_password)
        mail.select("inbox")
    except Exception as e:
        print(f"Error connecting to email server: {e}")
        return

    # Search for unread emails from the specific housing sender
    status, messages = mail.search(None, f'(UNSEEN FROM "{sender_address}")')

    if status != "OK":
        print("Error searching for emails.")
        mail.logout()
        return

    email_ids = messages[0].split()
    if not email_ids:
        print("No new package emails found.")
        mail.logout()
        return

    print(f"Found {len(email_ids)} new package email(s).")

    for email_id in email_ids:
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            print(f"Error fetching email ID {email_id.decode()}.")
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        html_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_body = part.get_payload(decode=True).decode()
                    break
        else:
            if msg.get_content_type() == "text/html":
                html_body = msg.get_payload(decode=True).decode()

        if not html_body:
            print("Could not find HTML content in the email.")
            continue

        package_info = parse_package_info(html_body)

        if package_info:
            print(f"Parsed package with Tracking No: {package_info['tracking_id']}")
            submit_package_form(form_url, package_info, user_info)
        else:
            print(
                f"Could not parse a valid tracking number from email ID {email_id.decode()}."
            )

    mail.close()
    mail.logout()


def parse_package_info(email_html: str) -> dict | None:
    """
    @brief Parses the email's HTML body to extract the tracking number.
    @param email_html The HTML content of the email.
    @return A dictionary with the tracking number, or None if not found.
    """
    try:
        soup = BeautifulSoup(email_html, "lxml")
        tracking_tag = soup.find(
            "strong", string=lambda text: text and "TRACKING NO:" in text.upper()
        )

        if tracking_tag:
            tracking_number = tracking_tag.next_sibling
            if tracking_number:
                return {"tracking_id": tracking_number.strip()}
    except Exception as e:
        print(f"An error occurred during HTML parsing: {e}")

    return None


def submit_package_form(url: str, package_info: dict, user_info: dict):
    """
    @brief Uses Playwright to navigate to the Cognito Form and submit package details.
    @param url The URL of the web form.
    @param package_info A dictionary containing the parsed package data.
    @param user_info A dictionary with the user's details.
    """
    tracking_id = package_info["tracking_id"]
    print(f"Submitting form for Tracking No: {tracking_id}...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")

            page.locator('[placeholder="First"]').fill(user_info["FIRST_NAME"])
            page.locator('[placeholder="Last"]').fill(user_info["LAST_NAME"])
            page.get_by_label("Room Number").fill(user_info["ROOM_NUMBER"])
            page.get_by_label("Tracking No").fill(tracking_id)

            page.get_by_role("button", name="Submit").click()

            page.wait_for_load_state("domcontentloaded")
            print("Form submitted successfully.")

            # Save a screenshot for confirmation/debugging
            page.screenshot(path=f"submission_{tracking_id}.png")
            browser.close()

    except Exception as e:
        print(f"An error occurred during form submission: {e}")


if __name__ == "__main__":
    check_for_new_packages()
