"""
CRM Company Deduplication Engine

A CRM-agnostic company deduplication system with:
- Deterministic matching: domain (including Additional Domains), LinkedIn URL, phone.
- Probabilistic matching: company name is primary; location + industry are supporting.
- Blocking by normalized domain and name prefix to keep comparisons tractable.
- Additional Domains expansion: HubSpot stores alternate domains per company —
  e.g. "zapier.com" might have "send.zapier.com" as the main domain with
  "zapier.com" in Additional Domains.  We expand all domains into the index.
- Configurable thresholds and similarity weights.
- Load from CSV or JSON (e.g. HubSpot API export).
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from urllib.parse import urlparse
import logging
from itertools import combinations
from collections import defaultdict
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MatchType(Enum):
    """Types of duplicate matches with confidence levels"""
    DETERMINISTIC_HIGH = "deterministic_high"      # 95%+ confidence (domain, LinkedIn)
    DETERMINISTIC_MEDIUM = "deterministic_medium"  # 85-95% confidence (name+location)
    PROBABILISTIC_HIGH = "probabilistic_high"      # 70-85% confidence
    PROBABILISTIC_MEDIUM = "probabilistic_medium"  # 55-70% confidence


class ActionType(Enum):
    """Recommended actions for duplicate clusters"""
    AUTO_MERGE = "auto_merge"        # Safe to merge automatically
    REVIEW_MERGE = "review_merge"    # Requires human review
    MANUAL_REVIEW = "manual_review"  # Complex case needing investigation


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate match between two companies"""
    company_1_id: str
    company_2_id: str
    match_type: MatchType
    confidence_score: float
    matching_fields: List[str]
    explanation: str
    survivor_recommendation: Optional[str] = None


@dataclass
class CompanyRecord:
    """Canonical company record structure"""
    # Core Identity
    record_id: str
    name: Optional[str] = None
    domain: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    phone: Optional[str] = None

    # Additional domains (HubSpot stores alternate domains)
    additional_domains: List[str] = field(default_factory=list)
    # All domains for this company (primary + additional, normalized)
    all_domains: Set[str] = field(default_factory=set)

    # Location
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None

    # Firmographic
    industry: Optional[str] = None
    employee_count: Optional[int] = None

    # CRM Metadata
    owner_id: Optional[str] = None
    lead_status: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    create_date: Optional[str] = None
    last_modified_date: Optional[str] = None
    last_activity_date: Optional[str] = None

    # Association counts
    num_associated_contacts: Optional[int] = None
    num_associated_deals: Optional[int] = None
    num_form_submissions: Optional[int] = None

    # Quality Metrics
    completeness_score: float = 0.0
    engagement_score: float = 0.0
    data_quality_score: float = 0.0

    # Raw data for custom properties
    raw_data: Dict = field(default_factory=dict)


# ── Company name suffixes to strip for matching ──────────────────────
COMPANY_SUFFIXES = re.compile(
    r'\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|'
    r'plc|lp|llp|gmbh|ag|sa|sarl|srl|bv|nv|pty|pvt|'
    r'group|holdings|international|intl|associates|partners|'
    r'hospital|medical center|health system|healthcare|health)\b\.?',
    re.IGNORECASE,
)

# Abbreviation normalization for company names
COMPANY_ABBREVIATIONS = {
    'univ': 'university',
    'hosp': 'hospital',
    'med': 'medical',
    'ctr': 'center',
    'dept': 'department',
    'natl': 'national',
    'intl': 'international',
    'assoc': 'associates',
    'svcs': 'services',
    'svc': 'service',
    'mgmt': 'management',
    'mfg': 'manufacturing',
    'tech': 'technology',
    'sys': 'system',
    'govt': 'government',
    'amer': 'american',
}


DEFAULT_ENGINE_CONFIG = {
    "similarity_weights": {
        "name": 0.45,
        "location": 0.25,
        "industry": 0.15,
        "phone": 0.10,
        "employee_count": 0.05,
    },
    "probabilistic_high_threshold": 0.82,
    "probabilistic_medium_threshold": 0.72,
    "min_name_similarity": 0.85,
    # When few corroborating fields exist, require stronger name match
    "sparse_min_name_similarity": 0.92,
    # Minimum contributing fields for a probabilistic match
    "min_matching_dimensions": 2,
    "use_blocking": True,
    "blocking_min_candidates": 30,
}


# ── Generic name prefixes that cause false positives ─────────────────
# These words are so common that two companies starting with the same
# prefix often are NOT the same entity (e.g. "University of X" vs
# "University of Y").  We require stronger evidence when both names
# start with one of these tokens.
GENERIC_NAME_PREFIXES = {
    'university', 'hospital', 'children', 'childrens', 'baptist',
    'memorial', 'community', 'north', 'south', 'east', 'west',
    'mount', 'saint', 'regional', 'national', 'american',
    'central', 'general', 'medical', 'surgical', 'texas',
    'boston', 'new', 'san', 'santa', 'med', 'advent', 'advocate',
    'northern', 'southern', 'eastern', 'western', 'northeast',
    'northwest', 'southeast', 'southwest', 'commonwealth',
    'methodist', 'presbyterian', 'lutheran', 'catholic',
    'mercy', 'providence', 'sacred', 'good',
    'quebec', 'ontario',
}


class CompanyDeduplicationEngine:
    """Main company deduplication engine with deterministic and probabilistic matching."""

    def __init__(self, config: Optional[Dict] = None):
        self.companies: Dict[str, CompanyRecord] = {}

        # Indexes
        self.domain_index: Dict[str, Set[str]] = defaultdict(set)       # domain -> company IDs
        self.linkedin_index: Dict[str, Set[str]] = defaultdict(set)     # linkedin slug -> company IDs
        self.phone_index: Dict[str, Set[str]] = defaultdict(set)        # normalized phone -> company IDs
        self.name_block_index: Dict[str, Set[str]] = defaultdict(set)   # name prefix -> company IDs

        cfg = {**DEFAULT_ENGINE_CONFIG, **(config or {})}
        self._weights = cfg["similarity_weights"]
        self.PROBABILISTIC_HIGH_THRESHOLD = cfg["probabilistic_high_threshold"]
        self.PROBABILISTIC_MEDIUM_THRESHOLD = cfg["probabilistic_medium_threshold"]
        self._min_name_similarity = cfg.get("min_name_similarity", 0.80)
        self._sparse_min_name_similarity = cfg.get("sparse_min_name_similarity", 0.88)
        self._min_matching_dimensions = cfg.get("min_matching_dimensions", 1)
        self._use_blocking = cfg["use_blocking"]
        self._blocking_min_candidates = cfg["blocking_min_candidates"]

    # ── Data Loading ──────────────────────────────────────────────────

    def load_csv(self, file_path: str, column_mapping: Optional[Dict] = None) -> int:
        """Load companies from CSV with flexible column mapping"""
        logger.info(f"Loading companies from {file_path}")

        df = pd.read_csv(file_path)
        logger.info(f"Loaded {len(df)} rows from CSV")

        default_mapping = {
            # HubSpot CSV export (with spaces — matches the export)
            'Record ID': 'record_id',
            'Company name': 'name',
            'Company Domain Name': 'domain',
            'Website URL': 'website',
            'LinkedIn Company Page': 'linkedin_url',
            'Phone Number': 'phone',
            'Street Address': 'address',
            'City': 'city',
            'State/Region': 'state',
            'Postal Code': 'zip_code',
            'Country/Region': 'country',
            'Industry': 'industry',
            'Number of Employees': 'employee_count',
            'Lifecycle Stage': 'lifecycle_stage',
            'Company owner': 'owner_id',
            'Last Activity Date': 'last_activity_date',
            'Create Date': 'create_date',
            'Number of Associated Contacts': 'num_associated_contacts',
            'Number of Associated Deals': 'num_associated_deals',
            'Lead Status': 'lead_status',
            'Number of Form Submissions': 'num_form_submissions',
            'Additional Domains': 'additional_domains',
            # HubSpot API / internal names
            'hs_object_id': 'record_id',
            'name': 'name',
            'domain': 'domain',
            'website': 'website',
            'linkedin_company_page': 'linkedin_url',
            'hs_linkedin_handle': 'linkedin_url',
            'phone': 'phone',
            'address': 'address',
            'city': 'city',
            'state': 'state',
            'zip': 'zip_code',
            'country': 'country',
            'industry': 'industry',
            'numberofemployees': 'employee_count',
            'lifecyclestage': 'lifecycle_stage',
            'hubspot_owner_id': 'owner_id',
            'notes_last_updated': 'last_activity_date',
            'hs_lastmodifieddate': 'last_modified_date',
            'createdate': 'create_date',
            'num_associated_contacts': 'num_associated_contacts',
            'num_associated_deals': 'num_associated_deals',
            'hs_lead_status': 'lead_status',
            'hs_additional_domains': 'additional_domains',
            # Salesforce
            'Id': 'record_id',
            'Name': 'name',
            'Website': 'website',
            'Phone': 'phone',
            'BillingStreet': 'address',
            'BillingCity': 'city',
            'BillingState': 'state',
            'BillingPostalCode': 'zip_code',
            'BillingCountry': 'country',
            'Industry': 'industry',
            'NumberOfEmployees': 'employee_count',
            'OwnerId': 'owner_id',
        }

        if column_mapping:
            default_mapping.update(column_mapping)

        processed_count = 0
        for _, row in df.iterrows():
            try:
                company = self._row_to_company(row, default_mapping)
                if company and company.record_id:
                    self.companies[company.record_id] = company
                    self._index_company(company)
                    processed_count += 1
            except Exception as e:
                logger.warning(f"Error processing row: {e}")
                continue

        logger.info(f"Successfully processed {processed_count} companies")
        return processed_count

    # ── Internal: build records ───────────────────────────────────────

    def _row_to_company(self, row: pd.Series, mapping: Dict) -> Optional[CompanyRecord]:
        record_data = {}

        for csv_field, canonical_field in mapping.items():
            if csv_field in row and pd.notna(row[csv_field]):
                val = row[csv_field]
                if canonical_field in ('employee_count', 'num_associated_contacts',
                                       'num_associated_deals', 'num_form_submissions'):
                    try:
                        val = int(float(val))
                    except (ValueError, TypeError):
                        val = None
                if val is not None:
                    record_data[canonical_field] = val

        if 'record_id' not in record_data:
            record_data['record_id'] = str(row.name) if hasattr(row, 'name') else self._generate_id(row)
        else:
            record_data['record_id'] = str(record_data['record_id'])

        # Handle additional_domains — comes in as semicolon-separated string
        additional_domains_raw = record_data.pop('additional_domains', None)
        additional_domains = []
        if additional_domains_raw and isinstance(additional_domains_raw, str):
            for d in re.split(r'[;,\s]+', additional_domains_raw):
                d = d.strip().lower()
                if d and '.' in d:
                    additional_domains.append(d)

        raw_data = {}
        for fld, value in row.items():
            if fld not in mapping and pd.notna(value):
                raw_data[fld] = value

        # Build the CompanyRecord with only valid fields
        valid_fields = {
            k: v for k, v in record_data.items()
            if k in CompanyRecord.__dataclass_fields__
            and k not in ('raw_data', 'additional_domains', 'all_domains')
        }
        company = CompanyRecord(**valid_fields, additional_domains=additional_domains, raw_data=raw_data)
        self._normalize_company(company)
        self._calculate_quality_scores(company)
        return company

    # ── Normalization ─────────────────────────────────────────────────

    def _normalize_company(self, company: CompanyRecord):
        """Normalize company fields for consistent matching."""
        # Domain normalization
        if company.domain:
            company.domain = self._normalize_domain(company.domain)
        if company.website and not company.domain:
            company.domain = self._extract_domain_from_url(company.website)
        elif company.website:
            # Also extract from website as a backup domain
            website_domain = self._extract_domain_from_url(company.website)
            if website_domain and website_domain != company.domain:
                company.additional_domains.append(website_domain)

        # Build the all_domains set (primary + additional)
        company.all_domains = set()
        if company.domain:
            company.all_domains.add(company.domain)
        for d in company.additional_domains:
            nd = self._normalize_domain(d)
            if nd:
                company.all_domains.add(nd)

        # Name normalization
        if company.name:
            company.name = self._normalize_company_name(company.name)

        # LinkedIn normalization
        if company.linkedin_url:
            company.linkedin_url = self._normalize_linkedin_company_url(company.linkedin_url)

        # Phone normalization
        if company.phone:
            company.phone = self._normalize_phone(str(company.phone))

        # Location normalization
        if company.state:
            company.state = self._normalize_state(company.state)
        if company.city:
            company.city = company.city.strip().title()
        if company.country:
            company.country = company.country.strip().title()

    def _normalize_domain(self, domain: str) -> Optional[str]:
        """Normalize a domain: lowercase, strip www., strip protocol."""
        if not domain or not isinstance(domain, str):
            return None
        domain = domain.strip().lower()
        # If it looks like a URL, extract the domain
        if '://' in domain:
            domain = self._extract_domain_from_url(domain) or domain
        # Strip www.
        if domain.startswith('www.'):
            domain = domain[4:]
        # Strip trailing slashes/paths
        domain = domain.split('/')[0].strip()
        return domain if '.' in domain else None

    def _extract_domain_from_url(self, url: str) -> Optional[str]:
        """Extract domain from a URL."""
        if not url or not isinstance(url, str):
            return None
        url = url.strip().lower()
        if not re.match(r'^[a-zA-Z0-9+.-]+://', url):
            url = 'https://' + url
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc or parsed.path.split('/')[0]
            if not netloc:
                return None
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            return netloc if '.' in netloc else None
        except Exception:
            return None

    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name: strip suffixes, clean whitespace, title case."""
        if not name:
            return ""
        # Remove content in parentheses like "(AKA Wayne Hospital)" — keep for matching
        # but store the cleaned version
        name = name.strip()
        # Strip common suffixes
        cleaned = COMPANY_SUFFIXES.sub('', name)
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        # If stripping removed everything, keep original
        if not cleaned or len(cleaned) < 2:
            cleaned = name
        return cleaned.strip()

    def _normalize_linkedin_company_url(self, url: str) -> str:
        """Extract canonical LinkedIn company slug."""
        if not url:
            return ""
        url = url.lower().strip()
        # Match /company/<slug>
        match = re.search(r'linkedin\.com/company/([^/?#]+)', url)
        if match:
            return f"linkedin.com/company/{match.group(1)}"
        # Match /school/<slug> (universities)
        match = re.search(r'linkedin\.com/school/([^/?#]+)', url)
        if match:
            return f"linkedin.com/school/{match.group(1)}"
        return url

    def _normalize_phone(self, phone: str) -> Optional[str]:
        """Normalize phone to digits only, minimum 7 digits."""
        if not phone:
            return None
        digits = re.sub(r'[^\d]', '', str(phone))
        # Strip leading country code '1' for US/Canada
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        return digits if len(digits) >= 7 else None

    def _normalize_state(self, state: str) -> str:
        """Normalize state abbreviations to full names."""
        state_map = {
            'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
            'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
            'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
            'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
            'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
            'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
            'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
            'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
            'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
            'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
            'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
            'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
            'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District Of Columbia',
            'ON': 'Ontario', 'QC': 'Quebec', 'BC': 'British Columbia', 'AB': 'Alberta',
        }
        s = state.strip()
        return state_map.get(s.upper(), s.title())

    # ── Quality scores ────────────────────────────────────────────────

    def _calculate_quality_scores(self, company: CompanyRecord):
        """Calculate data quality metrics for a company."""
        key_fields = [
            company.name, company.domain, company.phone,
            company.city, company.state, company.industry,
            company.linkedin_url,
        ]
        filled_fields = sum(1 for f in key_fields if f and str(f).strip())
        company.completeness_score = filled_fields / len(key_fields)

        engagement_factors = []
        if company.last_activity_date:
            engagement_factors.append(1.0)
        if company.lead_status and str(company.lead_status).upper() in [
            'CONNECTED', 'OPEN_DEAL', 'IN_PROGRESS', 'OPEN', 'IN PROGRESS'
        ]:
            engagement_factors.append(1.0)
        if company.lifecycle_stage and str(company.lifecycle_stage).upper() in [
            'CUSTOMER', 'OPPORTUNITY', 'SALES ACCEPTED LEAD',
            'SALESQUALIFIEDLEAD', 'SALES QUALIFIED LEAD'
        ]:
            engagement_factors.append(1.0)
        if company.num_associated_deals and company.num_associated_deals > 0:
            engagement_factors.append(1.0)

        company.engagement_score = (
            float(np.mean(engagement_factors)) if engagement_factors else 0.0
        )
        company.data_quality_score = (
            company.completeness_score * 0.7 + company.engagement_score * 0.3
        )

    # ── Indexing ──────────────────────────────────────────────────────

    def _index_company(self, company: CompanyRecord):
        """Index company for fast lookup during matching."""
        rid = company.record_id

        # Domain index — ALL domains (primary + additional)
        for d in company.all_domains:
            if d:
                self.domain_index[d].add(rid)

        # LinkedIn index
        if company.linkedin_url:
            self.linkedin_index[company.linkedin_url].add(rid)

        # Phone index
        if company.phone:
            self.phone_index[company.phone].add(rid)

        # Name block index — first 4 chars of normalized name (lowercased, no spaces)
        block_key = self._block_key_name(company)
        if block_key:
            self.name_block_index[block_key].add(rid)

    def _block_key_name(self, company: CompanyRecord) -> Optional[str]:
        """Generate a blocking key from company name."""
        if not company.name:
            return None
        # Clean and take first 4 chars of alphabetic-only version
        cleaned = re.sub(r'[^a-z]', '', company.name.lower())
        if len(cleaned) < 3:
            return None
        return cleaned[:4]

    def _generate_id(self, row: pd.Series) -> str:
        key_fields = []
        for fld in ('Company name', 'Company Domain Name', 'name', 'domain'):
            if fld in row and pd.notna(row.get(fld)):
                key_fields.append(str(row[fld]))
        if key_fields:
            return hashlib.md5('|'.join(key_fields).encode()).hexdigest()[:12]
        return f"company_{row.name}" if hasattr(row, 'name') else f"company_{id(row)}"

    # ── Main dedup entry point ────────────────────────────────────────

    def find_duplicates(self) -> List[DuplicateMatch]:
        """Run all deduplication stages and return matches."""
        logger.info("Starting company deduplication process...")
        matches = []

        # Step 1: Deterministic matching
        deterministic_matches = self._find_deterministic_matches()
        matches.extend(deterministic_matches)
        logger.info(f"Found {len(deterministic_matches)} deterministic matches")

        # Step 2: Probabilistic matching (excluding already matched pairs)
        matched_pairs: Set[Tuple[str, str]] = set()
        for m in deterministic_matches:
            pair = (min(m.company_1_id, m.company_2_id), max(m.company_1_id, m.company_2_id))
            matched_pairs.add(pair)

        probabilistic_matches = self._find_probabilistic_matches(exclude_pairs=matched_pairs)
        matches.extend(probabilistic_matches)
        logger.info(f"Found {len(probabilistic_matches)} probabilistic matches")

        # Step 3: Add survivor recommendations
        for match in matches:
            match.survivor_recommendation = self._recommend_survivor(
                match.company_1_id, match.company_2_id
            )

        logger.info(f"Total matches found: {len(matches)}")
        return matches

    # ── Deterministic matching ────────────────────────────────────────

    def _find_deterministic_matches(self) -> List[DuplicateMatch]:
        """Find high-confidence matches based on exact field matches."""
        matches = []
        seen_pairs: Set[Tuple[str, str]] = set()

        def _canon_pair(a: str, b: str) -> Tuple[str, str]:
            return (min(a, b), max(a, b))

        # 1. Domain-based matching (highest confidence for companies)
        # Two companies that share ANY domain are very likely the same entity
        for domain, company_ids in self.domain_index.items():
            if len(company_ids) > 1:
                ids_list = list(company_ids)
                for i, id1 in enumerate(ids_list):
                    for id2 in ids_list[i+1:]:
                        pair = _canon_pair(id1, id2)
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)
                        matches.append(DuplicateMatch(
                            company_1_id=pair[0],
                            company_2_id=pair[1],
                            match_type=MatchType.DETERMINISTIC_HIGH,
                            confidence_score=0.97,
                            matching_fields=['domain'],
                            explanation=f"Shared domain: {domain}",
                        ))

        # 2. Cross-domain matching via Additional Domains overlap
        # Company A has domain X, Company B has X in Additional Domains (or vice versa)
        # This is already handled by the domain_index since we index all_domains.
        # But let's also catch subdomain relationships:
        # e.g., "send.zapier.com" should match "zapier.com"
        root_domain_index: Dict[str, Set[str]] = defaultdict(set)
        for cid, company in self.companies.items():
            for d in company.all_domains:
                root = self._get_root_domain(d)
                if root:
                    root_domain_index[root].add(cid)

        # Common institutional / government root domains that host MANY unrelated orgs
        # Sharing these doesn't imply the companies are the same entity.
        generic_root_domains = {
            'nhs.uk', 'gov.uk', 'gc.ca', 'gov.au',
            'qc.ca', 'on.ca', 'bc.ca', 'ab.ca',  # Canadian province domains
            'edu', 'gov', 'mil', 'org',  # bare TLDs
            'harvard.edu', 'stanford.edu', 'mcgill.ca',  # large universities
        }

        for root, company_ids in root_domain_index.items():
            if len(company_ids) > 1:
                # Skip very short root domains (like "ed.gov") and known generic roots
                if root in generic_root_domains:
                    continue
                # Root domain must be at least 5 characters (skip "uk", "ca", etc.)
                if len(root) < 5:
                    continue
                ids_list = list(company_ids)
                for i, id1 in enumerate(ids_list):
                    for id2 in ids_list[i+1:]:
                        pair = _canon_pair(id1, id2)
                        if pair in seen_pairs:
                            continue
                        # Only add if name similarity is reasonable
                        # (to avoid false positives on shared root domains
                        # like "va.gov" matching many government entities)
                        c1 = self.companies[id1]
                        c2 = self.companies[id2]
                        name_sim = self._name_similarity(c1, c2) if c1.name and c2.name else 0
                        if name_sim >= 0.75:
                            seen_pairs.add(pair)
                            matches.append(DuplicateMatch(
                                company_1_id=pair[0],
                                company_2_id=pair[1],
                                match_type=MatchType.DETERMINISTIC_HIGH,
                                confidence_score=0.93,
                                matching_fields=['root_domain', 'name'],
                                explanation=f"Same root domain '{root}' + similar name ({name_sim:.0%})",
                            ))

        # 3. LinkedIn URL matching
        # Skip very short or generic LinkedIn slugs that many different orgs might share
        # e.g., "linkedin.com/company/children" is too generic
        for linkedin, company_ids in self.linkedin_index.items():
            if len(company_ids) > 1:
                # Extract the slug part
                slug = linkedin.split('/')[-1] if '/' in linkedin else linkedin
                # Skip slugs that are too short (< 10 chars) or too generic
                # e.g. "children", "hospital" are too generic to be reliable
                if len(slug) < 10:
                    continue
                # Skip if too many companies share this LinkedIn (data quality issue)
                if len(company_ids) > 4:
                    continue
                ids_list = list(company_ids)
                for i, id1 in enumerate(ids_list):
                    for id2 in ids_list[i+1:]:
                        pair = _canon_pair(id1, id2)
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)
                        matches.append(DuplicateMatch(
                            company_1_id=pair[0],
                            company_2_id=pair[1],
                            match_type=MatchType.DETERMINISTIC_HIGH,
                            confidence_score=0.95,
                            matching_fields=['linkedin_url'],
                            explanation=f"Exact LinkedIn URL match: {linkedin}",
                        ))

        # 4. Phone-based matching (requires name confirmation)
        for phone, company_ids in self.phone_index.items():
            if len(company_ids) > 1:
                ids_list = list(company_ids)
                for i, id1 in enumerate(ids_list):
                    for id2 in ids_list[i+1:]:
                        pair = _canon_pair(id1, id2)
                        if pair in seen_pairs:
                            continue
                        c1 = self.companies[id1]
                        c2 = self.companies[id2]
                        # Require solid name similarity to avoid different companies
                        # that happen to share a phone (e.g. same building, same call center)
                        name_sim = self._name_similarity(c1, c2) if c1.name and c2.name else 0
                        if name_sim >= 0.75:
                            seen_pairs.add(pair)
                            matches.append(DuplicateMatch(
                                company_1_id=pair[0],
                                company_2_id=pair[1],
                                match_type=MatchType.DETERMINISTIC_MEDIUM,
                                confidence_score=0.88,
                                matching_fields=['phone', 'name'],
                                explanation=f"Same phone {phone} + similar name ({name_sim:.0%})",
                            ))

        return matches

    def _get_root_domain(self, domain: str) -> Optional[str]:
        """Extract root domain (last two parts) from a potentially subdomain'd domain.
        e.g., 'send.zapier.com' -> 'zapier.com'
              'med.usc.edu' -> 'usc.edu'
              'zapier.com' -> 'zapier.com'
        """
        if not domain:
            return None
        parts = domain.split('.')
        if len(parts) < 2:
            return None
        # Handle co.uk, com.au style TLDs
        country_tlds = {'co.uk', 'com.au', 'co.nz', 'co.za', 'com.br', 'co.in', 'co.jp'}
        suffix = '.'.join(parts[-2:])
        if suffix in country_tlds and len(parts) >= 3:
            return '.'.join(parts[-3:])
        return '.'.join(parts[-2:])

    # ── Probabilistic matching ────────────────────────────────────────

    def _get_probabilistic_candidate_pairs(
        self, exclude_pairs: Set[Tuple[str, str]]
    ) -> Set[Tuple[str, str]]:
        """Get candidate pairs for probabilistic matching using blocking."""
        company_ids = list(self.companies.keys())
        n = len(company_ids)

        if self._use_blocking and n >= self._blocking_min_candidates:
            pairs: Set[Tuple[str, str]] = set()

            # Block by name prefix (first 4 chars)
            for ids in self.name_block_index.values():
                ids_list = list(ids)
                if len(ids_list) < 2:
                    continue
                max_in_block = 150
                capped = ids_list[:max_in_block]
                for i, id1 in enumerate(capped):
                    for id2 in capped[i + 1:]:
                        pair = (min(id1, id2), max(id1, id2))
                        pairs.add(pair)

            pairs -= exclude_pairs
            return pairs
        else:
            pairs = set()
            for i, id1 in enumerate(company_ids):
                for id2 in company_ids[i + 1:]:
                    pair = (min(id1, id2), max(id1, id2))
                    if pair not in exclude_pairs:
                        pairs.add(pair)
            return pairs

    def _name_similarity(self, c1: CompanyRecord, c2: CompanyRecord) -> float:
        """Calculate name similarity between two companies."""
        if not c1.name or not c2.name:
            return 0.0
        return self._jaro_winkler_similarity(c1.name, c2.name)

    def _has_generic_name_prefix(self, c1: CompanyRecord, c2: CompanyRecord) -> bool:
        """Check if both companies share a generic name prefix that causes false positives."""
        if not c1.name or not c2.name:
            return False
        first_word_1 = re.sub(r'[^a-z]', '', c1.name.lower().split()[0]) if c1.name.strip() else ''
        first_word_2 = re.sub(r'[^a-z]', '', c2.name.lower().split()[0]) if c2.name.strip() else ''
        if not first_word_1 or not first_word_2:
            return False
        return first_word_1 == first_word_2 and first_word_1 in GENERIC_NAME_PREFIXES

    def _location_mismatch(self, c1: CompanyRecord, c2: CompanyRecord) -> bool:
        """Check if both companies have state data and the states clearly differ."""
        if c1.state and c2.state:
            return c1.state.lower().strip() != c2.state.lower().strip()
        return False

    def _find_probabilistic_matches(
        self, exclude_pairs: Set[Tuple[str, str]]
    ) -> List[DuplicateMatch]:
        """Find matches based on weighted field similarity."""
        matches = []
        candidate_pairs = self._get_probabilistic_candidate_pairs(exclude_pairs)
        logger.info(f"Probabilistic candidates: {len(candidate_pairs)} pairs")

        for (id1, id2) in candidate_pairs:
            c1 = self.companies[id1]
            c2 = self.companies[id2]

            # Require decent name agreement
            name_sim = self._name_similarity(c1, c2)
            if name_sim < self._min_name_similarity:
                continue

            # ── Generic name prefix guard ───────────────────────────
            # When both companies start with a common word like "University"
            # or "Baptist", require near-exact names to proceed.
            if self._has_generic_name_prefix(c1, c2):
                if name_sim < 0.94:
                    continue  # "University of X" vs "University of Y" → skip

            # ── Location mismatch penalty ───────────────────────────
            # If both have state data and they differ, require extremely
            # high name similarity — same name in a different state is
            # usually a different entity.
            if self._location_mismatch(c1, c2) and name_sim < 0.95:
                continue

            # Calculate composite similarity + count contributing dimensions
            similarity_score, dimensions = self._calculate_similarity(c1, c2)

            # When contacts are sparse (only name matches, nothing else),
            # require a higher bar
            if dimensions < self._min_matching_dimensions and name_sim < self._sparse_min_name_similarity:
                continue

            match_type, explanation = self._classify_probabilistic_match(
                similarity_score, c1, c2
            )

            if match_type and similarity_score >= self.PROBABILISTIC_MEDIUM_THRESHOLD:
                match = DuplicateMatch(
                    company_1_id=id1,
                    company_2_id=id2,
                    match_type=match_type,
                    confidence_score=similarity_score,
                    matching_fields=self._get_matching_fields(c1, c2),
                    explanation=explanation,
                )
                matches.append(match)

        return matches

    def _calculate_similarity(
        self, c1: CompanyRecord, c2: CompanyRecord
    ) -> Tuple[float, int]:
        """Calculate similarity. Returns (score, dimension_count)."""
        w = self._weights
        total_fixed_weight = sum(w.values())

        weighted_sum = 0.0
        dimensions = 0  # how many non-name fields contributed

        # Name (always evaluated)
        if c1.name and c2.name:
            name_sim = self._jaro_winkler_similarity(c1.name, c2.name)
            weighted_sum += name_sim * w["name"]
        else:
            return 0.0, 0

        # Location (composite of city + state + country)
        loc_sim = self._location_similarity(c1, c2)
        if loc_sim > 0:
            weighted_sum += loc_sim * w["location"]
            if loc_sim > 0.5:
                dimensions += 1

        # Industry
        if c1.industry and c2.industry:
            ind_sim = self._jaro_winkler_similarity(
                c1.industry.lower(), c2.industry.lower()
            )
            weighted_sum += ind_sim * w["industry"]
            if ind_sim > 0.7:
                dimensions += 1

        # Phone
        if c1.phone and c2.phone:
            phone_sim = 1.0 if c1.phone == c2.phone else 0.0
            weighted_sum += phone_sim * w["phone"]
            if phone_sim > 0.5:
                dimensions += 1

        # Employee count proximity
        if c1.employee_count and c2.employee_count:
            emp_sim = self._employee_count_similarity(c1.employee_count, c2.employee_count)
            weighted_sum += emp_sim * w["employee_count"]
            if emp_sim > 0.5:
                dimensions += 1

        score = weighted_sum / total_fixed_weight
        return min(score, 1.0), dimensions

    def _location_similarity(self, c1: CompanyRecord, c2: CompanyRecord) -> float:
        """Calculate composite location similarity."""
        scores = []

        if c1.city and c2.city:
            city_sim = self._jaro_winkler_similarity(c1.city.lower(), c2.city.lower())
            scores.append(city_sim * 0.5)

        if c1.state and c2.state:
            state_sim = 1.0 if c1.state.lower() == c2.state.lower() else 0.0
            scores.append(state_sim * 0.3)

        if c1.country and c2.country:
            country_sim = 1.0 if c1.country.lower() == c2.country.lower() else 0.0
            scores.append(country_sim * 0.2)

        return sum(scores) if scores else 0.0

    def _employee_count_similarity(self, count1: int, count2: int) -> float:
        """Calculate employee count similarity as ratio proximity."""
        if not count1 or not count2:
            return 0.0
        ratio = min(count1, count2) / max(count1, count2)
        return ratio  # e.g., 500/520 = 0.96, 500/50000 = 0.01

    # ── String similarity ─────────────────────────────────────────────

    def _jaro_winkler_similarity(self, s1: str, s2: str) -> float:
        """Calculate Jaro-Winkler similarity between two strings."""
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0

        s1, s2 = s1.lower(), s2.lower()
        len1, len2 = len(s1), len(s2)

        match_window = max(len1, len2) // 2 - 1
        if match_window < 0:
            match_window = 0

        s1_matches = [False] * len1
        s2_matches = [False] * len2

        matches = 0
        transpositions = 0

        for i in range(len1):
            start = max(0, i - match_window)
            end = min(i + match_window + 1, len2)
            for j in range(start, end):
                if s2_matches[j] or s1[i] != s2[j]:
                    continue
                s1_matches[i] = True
                s2_matches[j] = True
                matches += 1
                break

        if matches == 0:
            return 0.0

        k = 0
        for i in range(len1):
            if not s1_matches[i]:
                continue
            while not s2_matches[k]:
                k += 1
            if s1[i] != s2[k]:
                transpositions += 1
            k += 1

        jaro = (
            matches / len1 + matches / len2 + (matches - transpositions / 2) / matches
        ) / 3

        prefix_length = 0
        for i in range(min(len1, len2, 4)):
            if s1[i] == s2[i]:
                prefix_length += 1
            else:
                break

        return jaro + (0.1 * prefix_length * (1 - jaro))

    # ── Classification helpers ────────────────────────────────────────

    def _classify_probabilistic_match(
        self, score: float, c1: CompanyRecord, c2: CompanyRecord
    ) -> Tuple[Optional[MatchType], str]:
        if score >= self.PROBABILISTIC_HIGH_THRESHOLD:
            return (
                MatchType.PROBABILISTIC_HIGH,
                f"High similarity match (score: {score:.3f})",
            )
        elif score >= self.PROBABILISTIC_MEDIUM_THRESHOLD:
            return (
                MatchType.PROBABILISTIC_MEDIUM,
                f"Medium similarity match (score: {score:.3f})",
            )
        return None, ""

    def _get_matching_fields(self, c1: CompanyRecord, c2: CompanyRecord) -> List[str]:
        matching = []

        # Domain overlap
        if c1.all_domains & c2.all_domains:
            matching.append('domain')

        if c1.name and c2.name:
            if self._jaro_winkler_similarity(c1.name, c2.name) > 0.75:
                matching.append('name')

        if c1.linkedin_url and c2.linkedin_url and c1.linkedin_url == c2.linkedin_url:
            matching.append('linkedin_url')

        if c1.phone and c2.phone and c1.phone == c2.phone:
            matching.append('phone')

        if c1.city and c2.city:
            if self._jaro_winkler_similarity(c1.city.lower(), c2.city.lower()) > 0.85:
                matching.append('city')

        if c1.state and c2.state and c1.state.lower() == c2.state.lower():
            matching.append('state')

        if c1.industry and c2.industry:
            if self._jaro_winkler_similarity(c1.industry.lower(), c2.industry.lower()) > 0.85:
                matching.append('industry')

        return matching

    # ── Survivor selection ────────────────────────────────────────────

    def _recommend_survivor(self, id1: str, id2: str) -> str:
        c1 = self.companies[id1]
        c2 = self.companies[id2]
        score1 = self._calculate_survivor_score(c1)
        score2 = self._calculate_survivor_score(c2)
        return id1 if score1 >= score2 else id2

    def _calculate_survivor_score(self, company: CompanyRecord) -> float:
        """Score a company record for survivor selection.

        Weights:
            Data quality:          25%
            Activity recency:      25%
            Lifecycle stage:       15%
            Associated contacts:   15%
            Has owner:             10%
            Modified recency:      10%
        """
        score = 0.0

        # Data completeness (25%)
        score += company.data_quality_score * 0.25

        # Recency of last activity (25%)
        recency = 0.0
        if company.last_activity_date:
            try:
                activity_dt = pd.to_datetime(company.last_activity_date, utc=True)
                now = pd.Timestamp.now(tz='UTC')
                days_ago = (now - activity_dt).days
                recency = max(0.1, 1.0 - (days_ago / 400))
            except Exception:
                recency = 0.1
        score += recency * 0.25

        # Lifecycle stage (15%)
        stage_scores = {
            'CUSTOMER': 1.0, 'OPPORTUNITY': 0.9,
            'SALES ACCEPTED LEAD': 0.85,
            'SALESQUALIFIEDLEAD': 0.8, 'SALES QUALIFIED LEAD': 0.8,
            'MARKETING QUALIFIED LEAD': 0.7, 'MARKETINGQUALIFIEDLEAD': 0.7,
            'LEAD': 0.5, 'CONTACT': 0.3, 'SUBSCRIBER': 0.2,
        }
        if company.lifecycle_stage:
            stage_val = stage_scores.get(company.lifecycle_stage.upper(), 0.1)
            score += stage_val * 0.15

        # Associated contacts (15%) — more contacts = richer record
        if company.num_associated_contacts and company.num_associated_contacts > 0:
            # Cap at 20 contacts for scoring purposes
            contact_score = min(company.num_associated_contacts / 20, 1.0)
            score += contact_score * 0.15

        # Has an owner (10%)
        if company.owner_id and str(company.owner_id).strip() not in ('', 'unassigned'):
            score += 0.10

        # Has been modified recently (10%)
        mod_recency = 0.0
        if company.last_modified_date:
            try:
                mod_dt = pd.to_datetime(company.last_modified_date, utc=True)
                now = pd.Timestamp.now(tz='UTC')
                days_ago = (now - mod_dt).days
                mod_recency = max(0.1, 1.0 - (days_ago / 400))
            except Exception:
                mod_recency = 0.1
        score += mod_recency * 0.10

        return score

    # ── Clustering ────────────────────────────────────────────────────

    def create_clusters(self, matches: List[DuplicateMatch]) -> Dict[str, List[str]]:
        """Create connected component clusters from match pairs using DFS."""
        graph: Dict[str, Set[str]] = defaultdict(set)
        for match in matches:
            graph[match.company_1_id].add(match.company_2_id)
            graph[match.company_2_id].add(match.company_1_id)

        visited: Set[str] = set()
        clusters = {}
        cluster_id = 0

        for company_id in graph:
            if company_id not in visited:
                cluster = self._dfs_cluster(graph, company_id, visited)
                if len(cluster) > 1:
                    clusters[f"cluster_{cluster_id}"] = sorted(list(cluster))
                    cluster_id += 1

        return clusters

    def _dfs_cluster(self, graph: Dict, start_id: str, visited: Set[str]) -> Set[str]:
        cluster: Set[str] = set()
        stack = [start_id]
        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                cluster.add(node)
                for neighbor in graph[node]:
                    if neighbor not in visited:
                        stack.append(neighbor)
        return cluster

    # ── Report generation ─────────────────────────────────────────────

    def generate_report(
        self, matches: List[DuplicateMatch], clusters: Dict[str, List[str]]
    ) -> Dict:
        total_companies = len(self.companies)
        total_matches = len(matches)
        total_clusters = len(clusters)
        companies_in_clusters = sum(len(c) for c in clusters.values())
        duplicates_to_remove = companies_in_clusters - total_clusters

        match_type_counts = {}
        for mt in MatchType:
            count = sum(1 for m in matches if m.match_type == mt)
            match_type_counts[mt.value] = count

        action_recommendations = {}
        for match in matches:
            if match.match_type == MatchType.DETERMINISTIC_HIGH:
                action = ActionType.AUTO_MERGE
            elif match.match_type == MatchType.DETERMINISTIC_MEDIUM:
                action = ActionType.REVIEW_MERGE
            elif match.match_type == MatchType.PROBABILISTIC_HIGH:
                action = ActionType.REVIEW_MERGE
            else:
                action = ActionType.MANUAL_REVIEW

            action_recommendations[
                f"{match.company_1_id}_{match.company_2_id}"
            ] = action.value

        report = {
            'summary': {
                'total_companies': total_companies,
                'total_matches': total_matches,
                'total_clusters': total_clusters,
                'duplicates_to_remove': duplicates_to_remove,
                'deduplication_rate': (
                    (duplicates_to_remove / total_companies * 100)
                    if total_companies > 0
                    else 0
                ),
            },
            'match_breakdown': match_type_counts,
            'matches': [
                {
                    'company_1_id': m.company_1_id,
                    'company_2_id': m.company_2_id,
                    'match_type': m.match_type.value,
                    'confidence_score': round(m.confidence_score, 3),
                    'matching_fields': m.matching_fields,
                    'explanation': m.explanation,
                    'survivor_recommendation': m.survivor_recommendation,
                    'recommended_action': action_recommendations.get(
                        f"{m.company_1_id}_{m.company_2_id}",
                        ActionType.MANUAL_REVIEW.value,
                    ),
                }
                for m in matches
            ],
            'clusters': clusters,
            'generated_at': pd.Timestamp.now().isoformat(),
        }

        return report

    # ── Export ─────────────────────────────────────────────────────────

    def export_results(self, report: Dict, output_path: str):
        json_path = (
            output_path.replace('.csv', '.json')
            if output_path.endswith('.csv')
            else f"{output_path}.json"
        )

        # Helper to serialize one company for the UI
        def _company_dict(c):
            return {
                "id": c.record_id,
                "name": c.name or "\u2014",
                "domain": c.domain or "\u2014",
                "website": c.website or "\u2014",
                "phone": c.phone or "\u2014",
                "linkedin_url": c.linkedin_url or "\u2014",
                "city": c.city or "\u2014",
                "state": c.state or "\u2014",
                "country": c.country or "\u2014",
                "industry": c.industry or "\u2014",
                "employee_count": c.employee_count or "\u2014",
                "lifecycle_stage": c.lifecycle_stage or "\u2014",
                "last_activity_date": c.last_activity_date or "\u2014",
                "last_modified_date": c.last_modified_date or "\u2014",
                "owner_id": c.owner_id or "\u2014",
                "num_associated_contacts": c.num_associated_contacts or 0,
                "num_associated_deals": c.num_associated_deals or 0,
                "additional_domains": list(c.all_domains - {c.domain}) if c.domain else list(c.all_domains),
                "survivor_score": round(self._calculate_survivor_score(c), 4),
                "data_quality_score": round(c.data_quality_score, 4),
            }

        # Enrich matches with company details for UI
        enriched_matches = []
        for match in report["matches"]:
            m = dict(match)
            for key in ("company_1_id", "company_2_id"):
                cid = m.get(key)
                c = self.companies.get(cid) or self.companies.get(str(cid))
                prefix = "company_1" if key == "company_1_id" else "company_2"
                if c:
                    m[f"{prefix}_name"] = c.name or "\u2014"
                    m[f"{prefix}_domain"] = c.domain or "\u2014"
                    m[f"{prefix}_phone"] = c.phone or "\u2014"
                    m[f"{prefix}_city"] = c.city or "\u2014"
                    m[f"{prefix}_state"] = c.state or "\u2014"
                    m[f"{prefix}_industry"] = c.industry or "\u2014"
                else:
                    for sfx in ('name', 'domain', 'phone', 'city', 'state', 'industry'):
                        m[f"{prefix}_{sfx}"] = "\u2014"
            enriched_matches.append(m)

        # Build companies dict for cluster view
        companies_in_clusters = set()
        for member_ids in report["clusters"].values():
            for mid in member_ids:
                companies_in_clusters.add(mid)
                companies_in_clusters.add(str(mid))

        companies_dict = {}
        for cid in companies_in_clusters:
            c = self.companies.get(cid) or self.companies.get(str(cid))
            if c and str(c.record_id) not in companies_dict:
                companies_dict[str(c.record_id)] = _company_dict(c)

        report_for_json = {**report, "matches": enriched_matches, "companies": companies_dict}
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_for_json, f, indent=2)

        # CSV export
        csv_path = (
            output_path.replace('.json', '.csv')
            if output_path.endswith('.json')
            else f"{output_path}.csv"
        )

        matches_data = []
        for match in report['matches']:
            c1 = self.companies.get(match['company_1_id'])
            c2 = self.companies.get(match['company_2_id'])
            if not c1 or not c2:
                continue
            matches_data.append({
                'Company_1_ID': match['company_1_id'],
                'Company_1_Name': c1.name or '',
                'Company_1_Domain': c1.domain or '',
                'Company_1_City': c1.city or '',
                'Company_2_ID': match['company_2_id'],
                'Company_2_Name': c2.name or '',
                'Company_2_Domain': c2.domain or '',
                'Company_2_City': c2.city or '',
                'Match_Type': match['match_type'],
                'Confidence_Score': match['confidence_score'],
                'Matching_Fields': ', '.join(match['matching_fields']),
                'Explanation': match['explanation'],
                'Survivor_Recommendation': match['survivor_recommendation'],
                'Recommended_Action': match['recommended_action'],
            })

        matches_df = pd.DataFrame(matches_data)
        matches_df.to_csv(csv_path, index=False)

        logger.info(f"Results exported to {json_path} and {csv_path}")
        return json_path, csv_path


# ── CLI entry point ───────────────────────────────────────────────────

def main(
    input_path: Optional[str] = None,
    output_path: str = "company_deduplication_results",
    config: Optional[Dict] = None,
):
    """Run the Company Deduplication Engine on a CSV file."""
    engine = CompanyDeduplicationEngine(config=config)
    input_path = input_path or "GTM Hackathon - hubspot-crm-exports-company-dedupe-export-2026-02-10.csv"

    try:
        company_count = engine.load_csv(input_path)
        logger.info(f"Loaded {company_count} companies")

        matches = engine.find_duplicates()
        clusters = engine.create_clusters(matches)
        report = engine.generate_report(matches, clusters)

        summary = report["summary"]
        print("\n=== COMPANY DEDUPLICATION SUMMARY ===")
        print(f"Total Companies: {summary['total_companies']}")
        print(f"Potential Matches: {summary['total_matches']}")
        print(f"Duplicate Clusters: {summary['total_clusters']}")
        print(f"Duplicates to Remove: {summary['duplicates_to_remove']}")
        print(f"Deduplication Rate: {summary['deduplication_rate']:.2f}%")

        print("\n=== MATCH BREAKDOWN ===")
        for match_type, count in report["match_breakdown"].items():
            if count > 0:
                print(f"  {match_type}: {count}")

        # Show some example matches
        print("\n=== SAMPLE MATCHES ===")
        for m in report["matches"][:10]:
            c1 = engine.companies.get(m['company_1_id'])
            c2 = engine.companies.get(m['company_2_id'])
            n1 = c1.name if c1 else '?'
            n2 = c2.name if c2 else '?'
            d1 = c1.domain if c1 else '?'
            d2 = c2.domain if c2 else '?'
            print(f"  {n1} ({d1}) <-> {n2} ({d2})")
            print(f"    {m['match_type']} | {m['confidence_score']} | {m['explanation']}")

        json_path, csv_path = engine.export_results(report, output_path)
        print(f"\nResults exported to: {json_path}, {csv_path}")
        return report
    except FileNotFoundError:
        logger.error(
            f"File not found: {input_path}. Provide a path to a CSV company file."
        )
        return None
    except Exception as e:
        logger.error(f"Error in company deduplication process: {e}")
        raise


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    main(input_path=path)
