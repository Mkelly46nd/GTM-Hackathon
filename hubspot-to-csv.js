/**
 * Convert HubSpot contacts JSON (e.g. contacts-last-activity-unknown.json) to CSV
 * for importing into Clay (or any tool). Run: node hubspot-to-csv.js
 */

import { readFileSync, writeFileSync } from 'fs';

const jsonPath = './contacts-last-activity-unknown.json';
const csvPath = './contacts-for-clay.csv';

const raw = readFileSync(jsonPath, 'utf-8');
const data = JSON.parse(raw);
const results = data.results || [];

const headers = ['id', 'email', 'firstname', 'lastname', 'company', 'createdate', 'lifecyclestage', 'hubspot_url'];

function escapeCsv(val) {
  if (val == null || val === '') return '';
  const s = String(val);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

const rows = results.map((r) => {
  const p = r.properties || {};
  return [
    r.id,
    p.email,
    p.firstname,
    p.lastname,
    p.company,
    p.createdate,
    p.lifecyclestage,
    r.url || '',
  ].map(escapeCsv);
});

const csv = [headers.join(','), ...rows.map((row) => row.join(','))].join('\n');
writeFileSync(csvPath, csv, 'utf-8');

console.log(`Wrote ${results.length} contacts to ${csvPath}`);
console.log('Import in Clay: open your table → Actions → Import → Upload CSV → choose this file and map columns.');
