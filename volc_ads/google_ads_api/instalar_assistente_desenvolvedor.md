> [!NOTE]
> **Note:** This tool is an open-source project and not an official Google product.

## Prerequisites

Before you begin, make sure you have the following:

1. **Google Ads API Access:**

   - A [Google Ads API developer token](https://developers.google.com/google-ads/api/docs/api-policy/developer-token).
   - A [Google Ads Configuration File](https://developers.google.com/google-ads/api/docs/client-libs#configuration) configured with your developer token, OAuth 2.0 credentials, and customer ID, located in your home directory. See the [client library configuration guide](https://developers.google.com/google-ads/api/docs/client-libs/python/configuration).
   - Familiarity with Google Ads API concepts and authentication.
2. **Software:**

   - [Python](https://www.python.org/downloads/) 3.10 or newer. Python is the default language, so you must have this installed and on your path.
   - [Google Antigravity command-line tool](https://antigravity.google/) installed.
   - [jq](https://stedolan.github.io/jq/download/) (command-line JSON processor). The installation script will attempt to install this if missing.
3. **Repository:**

   - A local clone of the [`google-ads-api-developer-assistant`](https://github.com/googleads/google-ads-api-developer-assistant) repository from GitHub.

## Get started

1. **Navigate to the project directory:**

       cd <full path>/google-ads-api-developer-assistant

   *(Note: If you have Antigravity shell integration enabled, entering this
   directory will automatically initialize the assistant session).*
2. **Run the install script:**
   This script initializes the development environment and clones the required
   Google Ads client libraries (Python is installed by default).

       ./install.sh

   If you are on Windows, run the `install.ps1` PowerShell script.
3. **Configure credentials:**
   Make sure your `google-ads.yaml` (or language equivalent) is placed in your
   home directory.

4. **Interact with the Assistant:**
   After the session is active, you can interact with the Assistant using
   natural language directly in your terminal.

## Key features

- **Natural language Q\&A:** Ask questions about Google Ads API features, best
  practices, or specific resources.

  - *"What are the available campaign types?"*
  - *"How do I filter by date in GAQL?"*
  - *"Explain the difference between click_view and impression_view."*
- **Code generation:** Generate GAQL queries and executable Python code
  snippets.

  - *"Show me campaigns with the most conversions in the last 30 days."*
  - *"Get all enabled ad group names for campaign ID 12345."*
  - *"Find disapproved ads across all campaigns."* Generated code is automatically linted using `ruff` and saved in the `saved/code/` directory.
- **Direct API execution:** Run generated read-only Python scripts directly
  within a sequestered virtual environment (`.venv`) and view formatted results as
  tables in your terminal.

  - Simply tell the Assistant: *"Run the code"* or *"Execute the script"*.
  - For safety, mutating operations (create, update, delete) are generated but **never** executed.
- **CSV export:** Save tabular results from API calls to a CSV file.

  - *"Save the results to a CSV file."* Files are saved in the `saved/csv/` directory.
- **Advanced diagnostics and troubleshooting:** Get help with error messages, unexpected API behavior, or offline conversion issues.

  - *"Why am I not seeing any results for my query?"*
  - *"Troubleshoot my conversions for customer 123-456-7890."* (Generates a detailed diagnostic report in `saved/data/`).
- **Additional context:** Add your own codebase or custom libraries for context.

  - Use the `update.sh` script with the `--context_path` option to register your project files: `none
    ./update.sh --context_path /path/to/your/codebase`
  - This allows the Assistant to include your application logic in its reasoning when creating responses or generating code in your preferred language.

## Example use cases

- **Reporting:**
  - *"Get me the top 5 keywords by cost for last month for customer 12345678."*
- **Account structure:**
  - *"List all campaign names and their IDs."*
- **Troubleshooting:**
  - *"I uploaded 100 conversions, but only 78 appear in the UI. How can I debug this using the API?"*
- **Learning:**
  - *"/explain what a shared set is"*
- **Code Generation:**
  - *"Write code to create a Performance Max campaign for <var translate="no">company name</var>."*

## Community and support

- **GitHub issues:** Report bugs, suggest features, or ask for help on the [Issues tab](https://github.com/googleads/google-ads-api-developer-assistant/issues) in the repository.
- **Discord:** Join the discussion in the `#ads-api-ai-tools` channel on the [Google Advertising and Measurement Community Discord server](https://goo.gle/google-ads-discord).
- **Feedback:** Share your feedback through this [survey form](https://goo.gle/feedback-googleadsapiassistant-li).

## Contribution guidelines

Contributions are welcome! See the `CONTRIBUTING.md` file in the GitHub
repository for guidelines.