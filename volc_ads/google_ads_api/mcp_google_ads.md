The **Model Context Protocol (MCP)** is an open standard that enables Large
Language Models (LLMs) to securely interact with external data and applications.
The **Google Ads MCP server** provides a standardized bridge to the Google Ads API,
which lets AI agents analyze and retrieve campaign data using natural language.

## Community resources and support

- **GitHub repository:** Find demos, examples, and report bugs or suggest
  features in the [google-ads-mcp repository](https://github.com/googleads/google-ads-mcp).

  Use the [Issues tab](https://github.com/googleads/google-ads-mcp/issues) for bug
  reports and feature requests.
- **Community:** Join the `#ads-api-ai-tools` channel on the
  [Google Advertising Community Discord](https://goo.gle/google-ads-discord).

## Technical overview

By implementing this MCP server, you eliminate the need to write custom "glue
code" for Google Ads API authentication, resource fetching, and data parsing.
The server exposes specific **tools** that an LLM can discover and invoke
autonomously.

### Key specifications

- **Protocol:** MCP (Model Context Protocol)
- **Mode:** **Read-only** (current release)
- **Language:** Python
- **Transport:** Standard input/output (`stdio`)
- **Authentication:** OAuth 2.0 or service account

### How the interaction loop works

1. **Request:** A user submits a query such as *"How is my campaign performance
   this week?"*.
2. **Discovery:** The LLM inspects its available tools and identifies the `google-ads-mcp` search capabilities.
3. **Execution:** The MCP server executes the underlying Python logic to query the Google Ads API.
4. **Context injection:** Structured results are returned to the LLM's context window.
5. **Response:** The LLM synthesizes the data into a human-readable answer.

## Get started

Follow these steps to configure and use the Google Ads MCP server.

### Prerequisites

Before configuration, ensure you have the following credentials from the
[Google Ads Developer console](https://developers.google.com/google-ads/api/docs/get-started/introduction):

- **Developer token:** Your unique 22-character access string.
- **Project ID:** Your Google Cloud project identifier.
- **OAuth credentials:** Either an OAuth2 Client ID/Client secret pair, or a set of [application default credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials).

### Configuration

To integrate the server into an MCP-compatible host, add the following entry to
your host's MCP configuration file, such as `settings.json`. Consult your host's
documentation for the exact location and filename of this configuration.

JSON

    {
      "mcpServers": {
        "google-ads-mcp": {
          "command": "pipx",
          "args": [
            "run",
            "--spec",
            "git+https://github.com/googleads/google-ads-mcp.git",
            "google-ads-mcp"
          ],
          "env": {
            "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
          }
        }
      }
    }

## Deployment on Google Cloud

Instead of hosting this MCP server locally, you can host it on Google Cloud Run
or on any other cloud-based infrastructure. This is useful if you want to share
the server across different agents or run it as a web service.

### Prerequisites

1. A Google Cloud project.
2. The [`gcloud` command-line tool](https://cloud.google.com/cli) installed,
   authenticated and with an active project configured:

       gcloud config set project YOUR_PROJECT_ID

### Build and push a Docker image

You can use Cloud Build to build and push the image to the Artifact Registry
without needing Docker installed locally.

1. Create a repository in Artifact Registry:

       gcloud artifacts repositories create mcp-servers --repository-format=docker --location=us-central1

2. Build and submit the image:

       gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcp-servers/google-ads-mcp:latest .

   Note that this step must be performed whenever you want to update the
   deployed server to the latest version.

### Deploy to Google Cloud Run

Make sure to set the required environment variables:

- `GOOGLE_PROJECT_ID`: Your Google Cloud project ID.
- `GOOGLE_ADS_DEVELOPER_TOKEN`: The [developer token](https://developers.google.com/google-ads/api/docs/api-policy/developer-token) you want the MCP server to use.
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_ID`: The OAuth Client ID you want the MCP server to use.
- `GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET`: The OAuth Client secret you want the MCP server to use.
- `GOOGLE_ADS_MCP_BASE_URL`: The base URL where your MCP server is accessible: this will be automatically assigned by Google Cloud Run after your first deployment. You can update the environment variables after deployment.
- `FASTMCP_HOST`: Set this to 0.0.0.0 to allow FastMCP to accept connections from all IP addresses.

    gcloud run deploy google-ads-mcp \
      --image us-central1-docker.pkg.dev/YOUR_PROJECT_ID/mcp-servers/google-ads-mcp:latest \
      --platform managed \
      --region us-central1 \
      --allow-unauthenticated \
      --set-env-vars="GOOGLE_PROJECT_ID=YOUR_PROJECT_ID,GOOGLE_ADS_DEVELOPER_TOKEN=YOUR_DEVELOPER_TOKEN,GOOGLE_ADS_MCP_OAUTH_CLIENT_ID=YOUR_CLIENT_ID,GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET=YOUR_CLIENT_SECRET,GOOGLE_ADS_MCP_BASE_URL=YOUR_BASE_URL,FASTMCP_HOST=0.0.0.0"

### Configure the MCP client

After deployment, update your MCP client configuration (for example,
`~/.gemini/settings.json`) to use the Cloud Run URL.

    {
      "mcpServers": {
        "google-ads-mcp": {
          "httpUrl": "https://your-cloud-run-url.a.run.app/mcp"
        }
      }
    }

## Core capabilities (tools)

The server exposes tools designed for account discovery and performance
reporting:

- **`list_accessible_customers`**: Returns the list of Google Ads customer IDs and account names accessible to the authenticated user.
- **`search`** : Executes [Google Ads Query Language (GAQL)](https://developers.google.com/google-ads/api/docs/query/overview) requests to fetch resource metrics, budgets, and status.
- **`get_resource_metadata`**: Retrieves metadata about a Google Ads API
  resource type, for example "campaign".

  This is useful to understand the structure of the data and what fields are
  available for querying.

> [!NOTE]
> **Note:** This implementation is strictly read-only. It cannot modify bids, pause campaigns, or create new assets.

## Sample prompts to start

**Ask what the server can do**:

    What can the google-ads-mcp server do?

**Ask about customers**:

    What customers do I have access to?

**Ask about campaigns**:

    How many active campaigns do I have?
    How is my campaign performance this week?
    Give me a report of the top spending campaigns split by device category over the
    last 7 days for account 1234567890