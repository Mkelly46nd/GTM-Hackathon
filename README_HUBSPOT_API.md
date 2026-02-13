# HubSpot API – Filter and pull records

Use the HubSpot CRM Search API to filter and pull **contacts**, **companies**, **deals**, and **tickets** from your account.

## 1. Get an access token (Private App)

1. In HubSpot go to **Settings** (gear) → **Integrations** → **Private Apps** (or **Development** → **Private Apps**).
2. Click **Create a private app**.
3. **Basic info**: name it (e.g. “GTM Hackathon API”).
4. **Scopes**: grant at least:
   - `crm.objects.contacts.read`
   - `crm.objects.companies.read`
   - `crm.objects.deals.read`
   - (and `crm.objects.tickets.read` if you use tickets).
5. Create the app and copy the **Access token** (starts with `pat-...`).

## 2. Configure the script

Create a `.env` file in this folder (copy from `.env.example`):

```bash
HUBSPOT_ACCESS_TOKEN=pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Or set the environment variable in your shell:

```bash
export HUBSPOT_ACCESS_TOKEN=pat-na1-...
```

On Windows (PowerShell):

```powershell
$env:HUBSPOT_ACCESS_TOKEN = "pat-na1-..."
```

To load `.env` automatically when running the script, you can use `dotenv`:

```bash
npm install dotenv
```

Then at the top of `hubspot-fetch.js` add:

```js
import 'dotenv/config';
```

## 3. Run the script

No extra npm install needed (uses Node built-in `fetch`; Node 18+).

```bash
# Default: 10 contacts
node hubspot-fetch.js

# 50 contacts
node hubspot-fetch.js contacts 50

# 20 companies
node hubspot-fetch.js companies 20

# 10 deals
node hubspot-fetch.js deals 10

# 5 tickets
node hubspot-fetch.js tickets 5
```

Output is JSON (all results plus total count).

## 4. Filtering records

Filters are set in `hubspot-fetch.js` in the `main()` function, in the `filterGroups` array. The HubSpot Search API uses **filter groups**: each group has **filters** (AND within the group); groups are OR’d together.

### Example filters

**Contacts with an email:**

```js
filterGroups: [
  {
    filters: [{ propertyName: 'email', operator: 'HAS_PROPERTY' }],
  },
],
```

**Contacts with email containing a domain:**

```js
filters: [{ propertyName: 'email', operator: 'CONTAINS_TOKEN', value: '*@acme.com' }]
```

**Deals with amount ≥ 1000:**

```js
filters: [{ propertyName: 'amount', operator: 'GTE', value: '1000' }]
```

**Companies created after a date:**

```js
filters: [{ propertyName: 'createdate', operator: 'GTE', value: '2024-01-01' }]
```

**Deals in a specific stage:**

```js
filters: [{ propertyName: 'dealstage', operator: 'EQ', value: 'closedwon' }]
```

**Multiple conditions (AND):** put multiple filters in the same group:

```js
filterGroups: [
  {
    filters: [
      { propertyName: 'amount', operator: 'GTE', value: '5000' },
      { propertyName: 'dealstage', operator: 'EQ', value: 'closedwon' },
    ],
  },
],
```

### Common operators

| Operator         | Meaning                    |
|------------------|----------------------------|
| `EQ`             | Equals                     |
| `NEQ`            | Not equals                 |
| `LT`, `LTE`      | Less than (or equal)       |
| `GT`, `GTE`      | Greater than (or equal)    |
| `CONTAINS_TOKEN` | Contains token (e.g. `*@x.com`) |
| `HAS_PROPERTY`   | Property is set            |
| `NOT_HAS_PROPERTY` | Property is not set     |

Property names are the **internal names** (e.g. `dealstage`, `createdate`). In HubSpot, check **Settings** → **Properties** for the object to see internal names.

## 5. Pagination

The API returns up to 100 results per request. To get more, use the `after` value from the response in the next request. You can extend `hubspot-fetch.js` to loop and pass `after` in the request body until no more results.

## 6. Using in your own code

You can import and call the search function from another script:

```js
import { searchHubSpot } from './hubspot-fetch.js';

const result = await searchHubSpot('deals', 25, {
  filterGroups: [
    {
      filters: [
        { propertyName: 'amount', operator: 'GTE', value: '1000' },
      ],
    },
  ],
});
console.log(result.results);
```

(You’ll need to export `searchHubSpot` from `hubspot-fetch.js` and keep the token in the environment.)

---

**Docs:** [HubSpot CRM Search](https://developers.hubspot.com/docs/api/crm/search), [Private apps](https://developers.hubspot.com/docs/api/private-apps)
