/**
 * Push HubSpot contacts from contacts-last-activity-unknown.json to a Clay table.
 * Requires CLAY_API_KEY and CLAY_TABLE_ID in .env
 * Run: node hubspot-to-clay.js
 */

try { await import('dotenv/config'); } catch {}

const CLAY_API_KEY = process.env.CLAY_API_KEY;
const CLAY_TABLE_ID = process.env.CLAY_TABLE_ID;
const JSON_PATH = './contacts-last-activity-unknown.json';

async function pushToClay() {
  if (!CLAY_API_KEY || !CLAY_TABLE_ID) {
    console.error('Set CLAY_API_KEY and CLAY_TABLE_ID in .env');
    process.exit(1);
  }

  const { readFileSync } = await import('fs');
  const data = JSON.parse(readFileSync(JSON_PATH, 'utf-8'));
  const results = data.results || [];

  const url = `https://api.clay.com/v3/tables/${CLAY_TABLE_ID}/records`;
  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${CLAY_API_KEY}`,
  };

  let ok = 0;
  let err = 0;

  for (const r of results) {
    const p = r.properties || {};
    const record = {
      id: `hubspot-${r.id}`,
      cells: {
        email: p.email ?? '',
        first_name: p.firstname ?? '',
        last_name: p.lastname ?? '',
        company: p.company ?? '',
        createdate: p.createdate ?? '',
        lifecyclestage: p.lifecyclestage ?? '',
        hubspot_url: r.url ?? '',
      },
    };

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ records: [record] }),
    });

    if (res.ok) {
      ok++;
      process.stdout.write('.');
    } else {
      err++;
      const text = await res.text();
      console.error(`\nFailed ${r.id}: ${res.status} ${text}`);
    }

    await new Promise((r) => setTimeout(r, 120));
  }

  console.log(`\nDone. Pushed ${ok} rows to Clay. Failed: ${err}`);
}

pushToClay().catch((e) => {
  console.error(e);
  process.exit(1);
});
