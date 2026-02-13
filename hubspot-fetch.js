/**
 * HubSpot API – filter and pull CRM records
 *
 * Usage:
 *   node hubspot-fetch.js                    # uses defaults: contacts, first 10
 *   node hubspot-fetch.js contacts 50        # 50 contacts
 *   node hubspot-fetch.js companies 20       # 20 companies
 *   node hubspot-fetch.js deals 10          # 10 deals
 *
 * Filtering: edit the filterGroups in searchHubSpot() or pass filters (see examples below).
 */

// Load .env if dotenv is installed: npm install dotenv
try { await import('dotenv/config'); } catch {}

const HUBSPOT_ACCESS_TOKEN = process.env.HUBSPOT_ACCESS_TOKEN;
const HUBSPOT_BASE = 'https://api.hubapi.com';

const OBJECT_TYPES = {
  contacts: 'contacts',
  companies: 'companies',
  deals: 'deals',
  tickets: 'tickets',
};

// Default properties to request per object (you can change these)
const DEFAULT_PROPERTIES = {
  contacts: ['email', 'firstname', 'lastname', 'company', 'createdate', 'lifecyclestage', 'notes_last_updated'],
  companies: ['name', 'domain', 'createdate', 'industry', 'numberofemployees'],
  deals: ['dealname', 'amount', 'dealstage', 'closedate', 'pipeline', 'createdate'],
  tickets: ['subject', 'content', 'hs_pipeline_stage', 'createdate', 'hubspot_owner_id'],
};

async function searchHubSpot(objectType, limit = 10, options = {}) {
  const { filterGroups = [], properties, sorts } = options;

  const url = `${HUBSPOT_BASE}/crm/v3/objects/${objectType}/search`;
  const body = {
    limit: Math.min(limit, 100),
    properties: properties || DEFAULT_PROPERTIES[objectType] || [],
    ...(filterGroups.length ? { filterGroups } : {}),
    ...(sorts?.length ? { sorts } : {}),
  };

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${HUBSPOT_ACCESS_TOKEN}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`HubSpot API ${res.status}: ${err}`);
  }

  return res.json();
}

export { searchHubSpot, OBJECT_TYPES, DEFAULT_PROPERTIES };

// ----- Example filters (uncomment or copy into your script) -----

// Contacts with email containing a domain:
// filterGroups: [{ filters: [{ propertyName: 'email', operator: 'CONTAINS_TOKEN', value: '*@acme.com' }] }]

// Deals with amount greater than 1000:
// filterGroups: [{ filters: [{ propertyName: 'amount', operator: 'GTE', value: '1000' }] }]

// Companies created after a date:
// filterGroups: [{ filters: [{ propertyName: 'createdate', operator: 'GTE', value: '2024-01-01' }] }]

// Deals in a specific stage (use your pipeline’s stage ID from HubSpot):
// filterGroups: [{ filters: [{ propertyName: 'dealstage', operator: 'EQ', value: 'closedwon' }] }]

async function main() {
  if (!HUBSPOT_ACCESS_TOKEN) {
    console.error('Set HUBSPOT_ACCESS_TOKEN (env or .env file). See README_HUBSPOT_API.md');
    process.exit(1);
  }

  const objectArg = (process.argv[2] || 'contacts').toLowerCase();
  const limitArg = parseInt(process.argv[3] || '10', 10) || 10;
  const filterPreset = (process.argv[4] || '').toLowerCase();
  const objectType = OBJECT_TYPES[objectArg] || OBJECT_TYPES.contacts;

  // Optional: add filters here (or use preset via 4th arg)
  let filterGroups = [];
  if (objectType === 'contacts' && filterPreset === 'last-activity-unknown') {
    // Contacts with no last activity date (unknown / never logged)
    filterGroups = [
      { filters: [{ propertyName: 'notes_last_updated', operator: 'NOT_HAS_PROPERTY' }] },
    ];
  }

  const result = await searchHubSpot(objectType, limitArg, {
    filterGroups: filterGroups.length ? filterGroups : undefined,
  });

  console.log(JSON.stringify(result, null, 2));
  console.error(`\nFetched ${result.results?.length ?? 0} ${objectType} (limit ${limitArg}).`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
