# HubSpot MCP in Cursor – Setup Guide

HubSpot has **two** MCP servers. Use the one that matches what you need:

| | **Developer MCP** (local) | **Remote MCP** (CRM data) |
|---|---------------------------|----------------------------|
| **Purpose** | App/CMS dev: CLI, docs, projects, deploy | Live CRM: contacts, companies, deals, tickets |
| **Runs** | On your machine via HubSpot CLI | HubSpot’s servers (mcp.hubspot.com) |
| **Works in Cursor today?** | **Yes** – no OAuth issues | **No** – HubSpot doesn’t allow `cursor://` redirect yet |

---

## Option 1: Developer MCP (use this in Cursor now)

This one **works in Cursor today**. It uses the HubSpot CLI and runs locally; no redirect URLs or OAuth.

### Prerequisites

1. **Join the beta:** [HubSpot Developer MCP server public beta](https://app.hubspot.com/l/product-updates/in-beta?rollout=239890).
2. **HubSpot CLI 7.6.0+**  
   - Check: `hs --version`  
   - Install/update: `npm install -g @hubspot/cli@latest`  
   - If you don’t have Node/npm, install [Node.js](https://nodejs.org/) first.

### Setup

1. Open a terminal (in Cursor or any shell).
2. Run:
   ```bash
   hs mcp setup
   ```
3. When prompted, choose **Cursor** (and any other IDEs you use).
4. **Restart Cursor** so it picks up the new MCP server.

### What you can do

- “Walk me through how to create a test account from the CLI”
- “Create a new project with app cards, a custom workflow action, and settings”
- “Help me add a React theme to my existing project”
- “Validate my project, then upload it to HubSpot”
- Search HubSpot dev docs, add modules/templates, deploy, and analyze app usage.

Best results with **Claude Sonnet 4 or newer** in Cursor.  
Docs: [HubSpot Developer MCP server](https://developers.hubspot.com/docs/developer-tooling/local-development/mcp-server).

---

## Option 2: Remote MCP (CRM data – blocked in Cursor for now)

Use this when you want **live CRM data** (contacts, companies, deals, tickets) in the AI.  
Currently **does not work in Cursor** because HubSpot’s UI only allows `http://` or `https://` redirect URLs, not `cursor://`. Use MCP Inspector or wait for HubSpot to support Cursor’s redirect.

### 1. Create an MCP Auth App in HubSpot

HubSpot’s form only accepts redirect URLs with `https://` or `http://`. Use this workaround so you can still use Cursor.

1. Log in to **HubSpot** and open **Settings** (gear icon).
2. In the left sidebar go to **Development**.
3. Under **Development**, open **MCP Auth Apps**.
4. Click **Create MCP auth app**.
5. Fill in:
   - **App name**: e.g. `Cursor MCP`
   - **Description**: optional
   - **Redirect URL**: Enter an **allowed** URL first so the form accepts it, for example:
     ```text
     http://localhost:6274/oauth/callback/debug
     ```
     (Spelling: use **callback**, not “callbc”.)
   - **Icon**: optional (can be skipped for personal use).
6. Click **Create**.
7. On the app details page:
   - Copy and save **Client ID** and **Client secret**.
   - In the **Redirect URLs** section, click **+ Add redirect URL** and add:
     ```text
     cursor://anysphere.cursor-mcp/oauth/callback
     ```
     If the form accepts it, you’re set. If it rejects `cursor://` (e.g. “must include https:// or http://”), leave the app as-is and try Cursor anyway (see troubleshooting below).

---

## 2. Add Your Credentials in Cursor

Your global MCP config is at:

**Windows:** `C:\Users\markk\.cursor\mcp.json`

Edit that file and replace the placeholders with your HubSpot values:

```json
{
  "mcpServers": {
    "hubspot": {
      "url": "https://mcp.hubspot.com/",
      "auth": {
        "CLIENT_ID": "paste-your-client-id-here",
        "CLIENT_SECRET": "paste-your-client-secret-here"
      }
    }
  }
}
```

**Optional (more secure):** use environment variables instead of putting secrets in the file:

1. Set `HUBSPOT_MCP_CLIENT_ID` and `HUBSPOT_MCP_CLIENT_SECRET` in your system or shell (e.g. in your Windows user environment variables or in your shell profile).
2. In `mcp.json` use:
   ```json
   "auth": {
     "CLIENT_ID": "${env:HUBSPOT_MCP_CLIENT_ID}",
     "CLIENT_SECRET": "${env:HUBSPOT_MCP_CLIENT_SECRET}"
   }
   ```

---

## 3. Restart Cursor and Authorize

1. Save `mcp.json` and **restart Cursor** (or reload the window).
2. The first time you use a HubSpot MCP tool, Cursor will start the OAuth flow.
3. In the browser:
   - Choose your HubSpot account.
   - Review and grant the requested permissions.
   - Complete the authorization.

After that, the HubSpot MCP server will be available in Cursor.

---

## What You Can Do With It

The HubSpot MCP server has **read-only** access to CRM data. You can ask the AI to:

- “Get the company record for [Company Name] from my HubSpot account.”
- “Summarize deals in the ‘Decision maker bought in’ stage with value > $1000.”
- “Show the last 5 tickets for [Contact Name].”
- “How many contacts does [Company] have?”
- “Get recent activity for Contact X.”

Data types include: contacts, companies, deals, tickets, invoices, products, line items, quotes, subscriptions, orders, carts, and users (and their associations).

---

## Troubleshooting

- **“Redirect URLs must include a protocol (https:// or http://)”**  
  HubSpot’s UI only accepts `http://` or `https://`. Create the app with e.g. `http://localhost:6274/oauth/callback/debug`, then in **Edit info** try adding `cursor://anysphere.cursor-mcp/oauth/callback`. If the edit form also rejects it, complete setup with the localhost URL, add your credentials to `mcp.json`, restart Cursor, and try the OAuth flow anyway—some providers accept registered custom schemes even when the form validation is strict. If Cursor’s OAuth still fails, HubSpot may not yet support `cursor://`; you can ask in [HubSpot’s developer community](https://community.hubspot.com/t5/APIs-Integrations/ct-p/APIs) or use [MCP Inspector](https://github.com/modelcontextprotocol/inspector) with the same app to test the connection.
- **Typo in redirect URL:** Use `callback` (with two l’s), not `callbc`.
- **Server not showing in Cursor:** Confirm `mcp.json` is in `C:\Users\markk\.cursor\` and that the JSON is valid (no missing commas or quotes). Then restart Cursor.
- **OAuth fails:** Make sure Client ID and Client Secret are correct and that the app is not disabled in HubSpot.

For more: [HubSpot MCP docs](https://developers.hubspot.com/mcp) and [Integrate with HubSpot MCP server](https://developers.hubspot.com/docs/apps/developer-platform/build-apps/integrate-with-hubspot-mcp-server).
