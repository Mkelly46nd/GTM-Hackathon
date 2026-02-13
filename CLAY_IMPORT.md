# Sending HubSpot contacts to a Clay table

## Option 1: CSV import (recommended, no API key)

1. **Generate the CSV** from your existing JSON file:
   ```bash
   node hubspot-to-csv.js
   ```
   This creates **`contacts-for-clay.csv`** with: id, email, firstname, lastname, company, createdate, lifecyclestage, hubspot_url.

2. **In Clay:**
   - Open the table you want to add rows to (or create a new table).
   - Click **Actions** → **Import** (or **Import data**).
   - Choose **Upload CSV** / **Import from CSV**.
   - Select `contacts-for-clay.csv` and map the CSV columns to your Clay columns (email → Email, firstname → First name, etc.).
   - Run the import.

Done. The 100 contacts are now in your Clay table.

---

## Option 2: Clay API (push rows programmatically)

Use this if you want to push from a script and have a Clay **API key** and **table ID**.

1. **Get your Clay API key:** Clay → **Settings** → **Account** → **API key**.
2. **Get your table ID:** Open the table in Clay; the table ID is in the URL (e.g. `clay.com/.../table/abc123...`) or in table settings.
3. **Create a table in Clay** with columns that match what you send (e.g. Email, First name, Last name, Company). Note the **column slugs** (often lowercase with underscores, e.g. `email`, `first_name`).
4. **Set env vars** (or use a `.env` file with `dotenv`):
   ```bash
   CLAY_API_KEY=your_api_key
   CLAY_TABLE_ID=your_table_id
   ```
5. **Run the push script:**
   ```bash
   node hubspot-to-clay.js
   ```

The script `hubspot-to-clay.js` reads `contacts-last-activity-unknown.json` and POSTs each contact to `https://api.clay.com/v3/tables/{TABLE_ID}/records` with `Authorization: Bearer YOUR_API_KEY`. Request body shape: `{ "records": [{ "id": "unique_id", "cells": { "email": "...", "first_name": "..." } }] }`. You may need to adjust column slugs to match your Clay table.

---

## Which option to use

- **CSV import:** Easiest, works with any Clay table, no API key. Use `hubspot-to-csv.js` then import the CSV in Clay.
- **API:** Good for automation or large/repeated syncs; requires API key and table ID and matching column slugs.
