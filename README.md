# Clark Dorm Package Automator

A Python script that automatically detects package notification emails and submits the package information to a web form. This project uses IMAP to read emails and Playwright to perform web automation.

## Features

- Connects to any IMAP-compatible email server (e.g., Gmail, Outlook).
- Searches for unread emails from a specific sender.
- Parses email content to extract package details using BeautifulSoup.
- Uses Playwright to automatically fill and submit a web form with the package details.
- Loads configuration from environment variables for security and portability.

## Local Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/clark-package-automator.git](https://github.com/your-username/clark-package-automator.git)
    cd clark-package-automator
    ```
2.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Install Playwright browsers:**
    ```bash
    playwright install
    ```
5.  **Configure for local execution:**

    - Create a file named `.env` in the project's root directory.
    - Copy the contents of the example below and fill in your details.

    ```
    # .env example for local testing
    IMAP_SERVER="imap.gmail.com"
    EMAIL_ADDRESS="your_email@gmail.com"
    # IMPORTANT: This must be a 16-digit App Password from your Google Account settings.
    EMAIL_APP_PASSWORD="your_16_digit_app_password"
    SENDER_ADDRESS="studentlife@studenthousing.org"
    FORM_URL="[https://www.cognitoforms.com/EHS1/StGeorgeTowersPackagePickupRequest](https://www.cognitoforms.com/EHS1/StGeorgeTowersPackagePickupRequest)"
    FIRST_NAME="YourFirstName"
    LAST_NAME="YourLastName"
    ROOM_NUMBER="1234"
    ```

## Deployment

This project is designed to run automatically using a **GitHub Actions** workflow. The workflow is defined in `.github/workflows/run-automator.yml`.

- The script runs on a schedule defined by a cron job.
- For deployment, environment variables are not loaded from the `.env` file. Instead, they must be configured as **Repository Secrets** in your GitHub project's settings (`Settings` > `Secrets and variables` > `Actions`). This is a secure way to provide credentials to the automated workflow.

## Usage

- **To run locally:**
  ```bash
  python main.py
  ```
