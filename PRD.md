# CRM Contact Deduplication Engine — Product Requirements Document

## 1. What This Is

A standalone contact deduplication system that identifies duplicate CRM records, groups them into clusters, picks the best record to keep (the "survivor"), and generates an actionable report. It runs locally against a CSV or JSON export — no CRM API writes, no destructive operations.

**Current state:** Working engine + visual report UI. Tested against 2,871 real HubSpot contacts from a healthcare GTM team. Detects 167 duplicate matches across 135 clusters with 98% coverage of known duplicates.

---

## 2. The Business Problem

Every CRM accumulates duplicate contacts over time. Common causes:

- **Job changers** — a nurse moves from Cleveland Clinic to ChristianaCare; the sales team creates a new record at the new org. Now there are two records for the same person.
- **Multiple entry points** — one rep enters a contact from a tradeshow, another imports the same person from a webinar list.
- **Inconsistent data entry** — `Jane Doe` vs `JANE DOE`, `jane.doe@hospital.com` vs `jdoe@hospital.com`.
- **Bulk imports** — CSV imports from marketing tools, event platforms, or purchased lists that overlap with existing contacts.

**Why this matters for GTM:**
- Reps waste time working the same person from different records
- Attribution and lifecycle tracking breaks when activity is split across duplicates
- Marketing sends the same person multiple emails (one per record), hurting sender reputation
- Pipeline reporting is inflated by double-counted contacts
- Lead routing assigns the same prospect to multiple reps

**Why not just use HubSpot's native dedup?**
HubSpot's built-in tool matches on name alone and surfaces 100+ potential duplicates — but with no confidence scoring, no prioritization, and no explanation of *why* two records match. You're left manually clicking through each pair. This engine adds algorithmic confidence, automatic survivor selection, and an actionable report that categorizes matches by quality so you can auto-merge the safe ones and only review the ambiguous cases.

---

## 3. How the Matching Algorithm Works

The engine uses a **staged pipeline** — each stage feeds into the next, from cheap/certain to expensive/probabilistic.

### Stage 0: Ingest & Normalize

Contacts are loaded from CSV (HubSpot export, Salesforce export, or generic) or JSON (HubSpot API response). Every record goes through normalization:

- **Names** — stripped of punctuation, title-cased (`DENNY QUINONES` → `Denny Quinones`)
- **Emails** — lowercased, trimmed
- **LinkedIn URLs** — extracted to canonical form (`linkedin.com/in/username`)
- **Company domains** — extracted from website URL or email domain (excluding personal email providers like Gmail, Yahoo, etc.)
- **Data quality score** — calculated per contact: 70% field completeness (how many of the 6 key fields are filled) + 30% engagement signals (has activity date, has advanced lifecycle stage)

### Stage 1: Indexing & Blocking

To avoid comparing every contact against every other contact (2,871 contacts = 4.1 million pairs), the engine builds lookup indexes:

- **Email index** — groups contacts by normalized email
- **LinkedIn index** — groups contacts by normalized LinkedIn URL
- **Name+domain index** — groups contacts by (last name + first initial, company domain)
- **Name-only blocks** — groups contacts by (last name + first initial) for probabilistic matching

This reduces the comparison space from millions of pairs down to a few hundred.

### Stage 2: Deterministic Matching

High-confidence matches based on exact field equality:

| Match Signal | Confidence | Example |
|---|---|---|
| Same email address | 98% | Both records have `jdoe@hospital.com` |
| Same LinkedIn URL | 96% | Both link to `linkedin.com/in/jdoe` |
| Same name + same company domain (emails don't conflict) | 88% | Both are "Jane Doe" at `hospital.com`, one has `jane.doe@` and the other has `jdoe@` |

**Key detail on email domain comparison:** Two contacts at the same company domain with *different* email addresses (e.g., `jane.doe@bigco.com` vs `jdoe@bigco.com`) are treated as potential duplicates — not rejected. Only contacts with emails at *different domains* are skipped in this stage.

### Stage 3: Probabilistic Matching

For pairs not caught by deterministic rules, the engine computes a **weighted similarity score**:

| Field | Weight | Method |
|---|---|---|
| Name (first + last) | 55% | Jaro-Winkler string similarity |
| Company name | 25% | Jaro-Winkler string similarity |
| Job title | 15% | Jaro-Winkler string similarity |
| Company domain | 5% | Exact match (1.0 or 0.0) |

The denominator is always the full weight (100%), so missing fields count as zero, not "skip." This prevents sparse records from getting inflated scores just because the only field present happens to match.

**Thresholds:**
- **Probabilistic High** (≥ 82%): strong match across multiple fields → `review_merge`
- **Probabilistic Medium** (≥ 68%): moderate match → `manual_review`
- **Minimum name similarity** (≥ 80%): names must be reasonably close or the pair is rejected outright
- **Sparse records** (only 1 non-name field matches): name similarity must be ≥ 90% to compensate for the lack of corroborating signals

### Stage 3b: Cross-Domain Matching (Job Changers)

This is the critical capability that outperforms basic name-only dedup. When two contacts have emails at **different domains** (different organizations), the engine still considers them a potential match if:

- Name similarity ≥ 95% (near-exact match to avoid false positives on common names like "David Kim")
- Confidence is set to `name_similarity × 0.85` (penalized because we can't corroborate with company/domain)
- Action is `manual_review` — these always require human confirmation

This catches the most common GTM data quality issue: **the same person appears in your CRM at two different companies because they changed jobs**.

### Stage 4: Clustering

Individual pair matches are grouped into **clusters** using graph traversal (DFS connected components). If A matches B, and B matches C, then {A, B, C} form a single cluster — even if A and C wouldn't match on their own.

This matters for contacts with 3+ duplicate records (15 clusters in our test data), like a person who appears at three different hospitals.

### Stage 5: Survivor Selection

For each cluster, the engine picks the "best" record to keep (the survivor) based on a weighted scoring model:

| Factor | Weight | Logic |
|---|---|---|
| Data completeness | 30% | More filled fields = higher score |
| Last activity recency | 30% | Most recently active contact wins (linear decay over 400 days) |
| Lifecycle stage | 20% | Customer > Opportunity > SQL > MQL > Lead > Subscriber |
| Has a contact owner | 10% | Assigned contacts score higher than unassigned |
| Last modified recency | 10% | More recently updated records score higher |

The survivor is the record that should be **kept**; the other records in the cluster should be **merged** into it (transferring any unique data, activity history, and associations).

### Stage 6: Report Generation

Results are exported as:
- **JSON** — full match data, cluster memberships, enriched contact details with survivor scores
- **CSV** — flat table of match pairs for spreadsheet analysis
- **HTML report** — interactive visual UI with two views:
  - **Pairs view** — sortable table of all match pairs with type, confidence, action badges
  - **Cluster view** — accordion-style groups showing all records in each cluster side-by-side, with "Keep" and "Merge" badges, survivor scores, lifecycle stages, and last activity dates

---

## 4. What We Have Today (v0.1)

### Working
- Full matching pipeline (deterministic + probabilistic + cross-domain)
- CRM-agnostic data loading (HubSpot CSV, HubSpot JSON API, Salesforce CSV column mapping)
- Clustering and survivor selection with date-based recency scoring
- Interactive HTML report with both pairs and cluster views
- Configurable thresholds and weights
- 98% coverage on real 2,871-contact healthcare dataset

### Not Built Yet
- No CRM write-back (no merging, no archiving)
- No API integration (runs on file exports only)
- No scheduled/automated runs
- No multi-user access or team workflow
- No merge conflict resolution (what happens when both records have different phone numbers?)
- No undo/rollback capability
- No integration with marketing automation (for email suppression during merge)

---

## 5. Open Questions for Next Stages

### Making This Useful for a GTM Team

**The gap between "finding duplicates" and "fixing them" is where all the value is.** The engine currently stops at identification + recommendation. To be truly useful, we need to answer:

1. **Merge execution** — How do duplicates actually get merged?
   - Option A: Generate a merge script that calls HubSpot API (automated but risky)
   - Option B: Generate a formatted CSV that can be bulk-imported back into HubSpot to update/archive records
   - Option C: Build a review UI where a human approves each cluster and clicks "merge" (safest but slowest)
   - Option D: Use HubSpot's native merge API for `auto_merge` confidence pairs, route `manual_review` to a human queue

2. **Merge rules** — When merging, what data wins?
   - The survivor's data takes priority by default, but what about fields that only exist on the non-survivor? (e.g., survivor has no phone, but the duplicate does)
   - Should we build a "best of both" merge that picks the most complete value for each field?
   - How do we handle conflicting values? (survivor says phone is 555-1234, duplicate says 555-5678)

3. **Activity and association preservation** — A merge must not lose:
   - Deal associations
   - Email/call/meeting activity history
   - List memberships
   - Workflow enrollment history
   - Form submissions
   - Does HubSpot's merge API handle all of these automatically?

4. **Ongoing dedup vs. one-time cleanup** —
   - One-time: run the engine, clean up, done
   - Ongoing: run weekly/monthly, catch new duplicates as they enter
   - Prevention: block duplicate creation at the point of entry (form submissions, imports, API creates)
   - Which mode matters most right now?

5. **Confidence calibration** —
   - The `manual_review` bucket (137 of 167 matches) is too large for a human to review efficiently
   - Can we break `manual_review` into sub-tiers (likely/unlikely) to prioritize?
   - Should we use additional signals (IP address, form submission source, deal associations) to boost confidence?

6. **Integration points** —
   - Should this run as a HubSpot workflow/custom action?
   - Should it be a standalone web app the ops team uses?
   - Should it feed into Clay for enrichment before merge decisions?
   - Should it connect to Slack/email to notify reps about their duplicate contacts?

7. **Scale** —
   - Current dataset: 2,871 contacts, runs in <1 second
   - At 50K contacts, the blocking strategy should still work but needs testing
   - At 500K+, we'd need to consider database-backed indexing or a streaming approach

---

## 6. Possible Product Roadmap

### Phase 1: Review & Approve Workflow (Current → Usable)
- Add an "approve/reject" button to each cluster in the HTML report
- Export approved merges as a structured action plan (JSON or CSV)
- Build a HubSpot merge script that takes the action plan and executes merges via API
- Add a "dry run" mode that shows what would change without executing

### Phase 2: Smarter Matching
- Add phone number matching (normalized, ignoring formatting)
- Add associated company matching (HubSpot company associations, not just company name strings)
- Add email alias matching (detect that `jdoe@` and `jane.doe@` at the same domain are likely the same person)
- Add "recently created" boosting (newly imported contacts are more likely to be duplicates)

### Phase 3: Automated Pipeline
- Schedule weekly runs via cron or HubSpot workflow trigger
- Auto-merge high-confidence pairs (deterministic_high only)
- Route medium/low confidence to a review queue
- Send Slack notifications to contact owners when their records are flagged

### Phase 4: Duplicate Prevention
- Webhook listener on HubSpot contact creation
- Real-time dedup check before a new record is saved
- Block or flag duplicate creation at the source
- Integration with form tools (Typeform, HubSpot forms) to catch duplicates at submission time

---

## 7. Technical Architecture

```
Input Sources                    Engine Pipeline                    Output
─────────────                    ───────────────                    ──────
HubSpot CSV Export ──┐
                     │    ┌─── Normalize ──── Index/Block ───┐
HubSpot JSON API ────┤    │                                  │
                     ├───►│    Deterministic Match            │
Salesforce CSV ──────┤    │         ↓                        │
                     │    │    Probabilistic Match            ├───► JSON Results
Generic CSV ─────────┘    │         ↓                        │        ↓
                          │    Cross-Domain Match             │     HTML Report
                          │         ↓                        │     CSV Export
                          │    Cluster (DFS)                  │
                          │         ↓                        │
                          └─── Survivor Selection ───────────┘
```

### Files

| File | Purpose |
|---|---|
| `contact_deduplication_engine.py` | Core engine — all matching, scoring, clustering, export logic |
| `deduplication_report.html` | Interactive UI — loads JSON results, renders pairs + cluster views |
| `deduplication_results.json` | Engine output — matches, clusters, enriched contacts with survivor scores |
| `deduplication_results.csv` | Flat match-pair table for spreadsheet analysis |
| `hubspot-fetch.js` | Node.js script to pull contacts from HubSpot API (pagination-limited, needs work) |
| `serve_report.py` | Local HTTP server to serve the HTML report (avoids CORS issues with file:// loading) |

### Key Config (tunable)

| Parameter | Default | What it controls |
|---|---|---|
| `min_name_similarity` | 0.80 | Floor for any name comparison |
| `sparse_min_name_similarity` | 0.90 | Higher bar when only name matches (no company/title corroboration) |
| `cross_domain_min_name_similarity` | 0.95 | Very high bar for matching across different organizations |
| `probabilistic_high_threshold` | 0.82 | Composite score needed for "high confidence" probabilistic match |
| `probabilistic_medium_threshold` | 0.68 | Composite score needed for "medium confidence" probabilistic match |
| Survivor weights | 30/30/20/10/10 | Data quality / Activity recency / Lifecycle / Owner / Modified recency |

---

## 8. Current Performance (2,871 contacts)

| Metric | Value |
|---|---|
| Total contacts processed | 2,871 |
| Matches found | 167 |
| Clusters formed | 135 |
| Clusters with 3+ records | 15 |
| Duplicates to merge | 151 |
| Deduplication rate | 5.26% |
| Coverage of known name-duplicates | 98% (126/129 groups) |
| Processing time | < 1 second |

### Match breakdown
- Deterministic High (auto-merge safe): 1
- Deterministic Medium (review merge): 14
- Probabilistic High (review merge): 15
- Probabilistic Medium (manual review): 137

### 3 remaining misses (edge cases)
1. **Debbie vs Debra Busby-Edebiri** — name similarity 0.87, below the 0.95 cross-domain threshold. Genuinely ambiguous: is "Debbie" a nickname for "Debra"?
2. **Jessica Pacheco Montes** — one record has no email, different company name. Not enough signal.
3. **Julie Carter** — same situation, one record missing email entirely.
