"""
CRM Contact Deduplication Engine

A CRM-agnostic contact deduplication system with:
- Deterministic matching: email, LinkedIn URL, and name+company_domain.
- Probabilistic matching: name is primary; company/title are supporting.
  - Different normalized emails => never a duplicate.
  - Minimum name similarity required (default 0.80); no "same domain only" matches.
  - Sparse contacts (few fields) require higher name similarity to compensate.
- Blocking by name (last + first initial), not by domain alone.
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
    DETERMINISTIC_HIGH = "deterministic_high"      # 95%+ confidence (email, LinkedIn)
    DETERMINISTIC_MEDIUM = "deterministic_medium"  # 80-95% confidence (name+domain)
    PROBABILISTIC_HIGH = "probabilistic_high"      # 70-80% confidence
    PROBABILISTIC_MEDIUM = "probabilistic_medium"  # 50-70% confidence


class ActionType(Enum):
    """Recommended actions for duplicate clusters"""
    AUTO_MERGE = "auto_merge"        # Safe to merge automatically
    REVIEW_MERGE = "review_merge"    # Requires human review
    MANUAL_REVIEW = "manual_review"  # Complex case needing investigation


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate match between two contacts"""
    contact_1_id: str
    contact_2_id: str
    match_type: MatchType
    confidence_score: float
    matching_fields: List[str]
    explanation: str
    survivor_recommendation: Optional[str] = None


@dataclass
class ContactRecord:
    """Canonical contact record structure"""
    # Core Identity
    record_id: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None

    # Company Context
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    company_domain: Optional[str] = None
    website: Optional[str] = None

    # CRM Metadata
    owner_id: Optional[str] = None
    lead_status: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    create_date: Optional[str] = None
    last_modified_date: Optional[str] = None
    last_activity_date: Optional[str] = None

    # Quality Metrics
    completeness_score: float = 0.0
    engagement_score: float = 0.0
    data_quality_score: float = 0.0

    # Raw data for custom properties
    raw_data: Dict = field(default_factory=dict)


DEFAULT_ENGINE_CONFIG = {
    "similarity_weights": {
        "name": 0.55,
        "company": 0.25,
        "title": 0.15,
        "domain": 0.05,
    },
    "probabilistic_high_threshold": 0.82,
    "probabilistic_medium_threshold": 0.68,
    "min_name_similarity": 0.80,
    # When few fields overlap, require stronger name match
    "sparse_min_name_similarity": 0.90,
    # Cross-domain: same name at different email domains (job changers).
    # Requires near-exact name to avoid false positives on common names.
    "cross_domain_min_name_similarity": 0.95,
    # Minimum contributing fields for a probabilistic match
    "min_matching_dimensions": 1,
    "use_blocking": True,
    "blocking_min_candidates": 50,
}


class ContactDeduplicationEngine:
    """Main deduplication engine with deterministic and probabilistic matching."""

    def __init__(self, config: Optional[Dict] = None):
        self.contacts: Dict[str, ContactRecord] = {}
        self.email_index: Dict[str, Set[str]] = defaultdict(set)
        self.linkedin_index: Dict[str, Set[str]] = defaultdict(set)
        self.domain_index: Dict[str, Set[str]] = defaultdict(set)
        self.name_domain_index: Dict[Tuple[str, str], Set[str]] = defaultdict(set)

        cfg = {**DEFAULT_ENGINE_CONFIG, **(config or {})}
        self._weights = cfg["similarity_weights"]
        self.PROBABILISTIC_HIGH_THRESHOLD = cfg["probabilistic_high_threshold"]
        self.PROBABILISTIC_MEDIUM_THRESHOLD = cfg["probabilistic_medium_threshold"]
        self._min_name_similarity = cfg.get("min_name_similarity", 0.80)
        self._sparse_min_name_similarity = cfg.get("sparse_min_name_similarity", 0.90)
        self._cross_domain_min_name_similarity = cfg.get("cross_domain_min_name_similarity", 0.95)
        self._min_matching_dimensions = cfg.get("min_matching_dimensions", 1)
        self._use_blocking = cfg["use_blocking"]
        self._blocking_min_candidates = cfg["blocking_min_candidates"]

    # ── Data Loading ──────────────────────────────────────────────────

    def load_csv(self, file_path: str, column_mapping: Optional[Dict] = None) -> int:
        """Load contacts from CSV with flexible column mapping"""
        logger.info(f"Loading contacts from {file_path}")

        df = pd.read_csv(file_path)
        logger.info(f"Loaded {len(df)} rows from CSV")

        default_mapping = {
            # HubSpot API / internal
            'firstname': 'first_name',
            'lastname': 'last_name',
            'email': 'email',
            'phone': 'phone',
            'hs_linkedin_url': 'linkedin_url',
            'company': 'company_name',
            'jobtitle': 'job_title',
            'hubspot_owner_id': 'owner_id',
            'hs_lead_status': 'lead_status',
            'lifecyclestage': 'lifecycle_stage',
            'createdate': 'create_date',
            'lastmodifieddate': 'last_modified_date',
            'lastactivitydate': 'last_activity_date',
            'hs_object_id': 'record_id',
            'website': 'website',
            'company_website': 'website',
            # HubSpot CSV export (with spaces)
            'First Name': 'first_name',
            'Last Name': 'last_name',
            'Record ID': 'record_id',
            'Email': 'email',
            'Phone Number': 'phone',
            'LinkedIn URL': 'linkedin_url',
            'Company Name': 'company_name',
            'Associated Company (Primary)': 'company_name',
            'Job Title': 'job_title',
            'Contact owner': 'owner_id',
            'Lead Status': 'lead_status',
            'Lifecycle Stage': 'lifecycle_stage',
            'Create Date': 'create_date',
            'Last Modified Date': 'last_modified_date',
            'Last Activity Date': 'last_activity_date',
            'Website URL': 'website',
            # Salesforce
            'FirstName': 'first_name',
            'LastName': 'last_name',
            'Id': 'record_id',
            'Phone': 'phone',
            'LinkedIn__c': 'linkedin_url',
            'Company': 'company_name',
            'Title': 'job_title',
            'OwnerId': 'owner_id',
            'LeadStatus': 'lead_status',
            'Website': 'website',
        }

        if column_mapping:
            default_mapping.update(column_mapping)

        processed_count = 0
        for _, row in df.iterrows():
            try:
                contact = self._row_to_contact(row, default_mapping)
                if contact and contact.record_id:
                    self.contacts[contact.record_id] = contact
                    self._index_contact(contact)
                    processed_count += 1
            except Exception as e:
                logger.warning(f"Error processing row: {e}")
                continue

        logger.info(f"Successfully processed {processed_count} contacts")
        return processed_count

    def load_json(
        self,
        file_path: str,
        results_key: str = "results",
        property_key: str = "properties",
        id_key: str = "id",
        column_mapping: Optional[Dict] = None,
    ) -> int:
        """Load contacts from JSON (e.g. HubSpot API export)."""
        logger.info(f"Loading contacts from JSON: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if results_key in data:
            items = data[results_key]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]

        default_mapping = {
            "firstname": "first_name",
            "lastname": "last_name",
            "email": "email",
            "phone": "phone",
            "hs_linkedin_url": "linkedin_url",
            "company": "company_name",
            "jobtitle": "job_title",
            "hubspot_owner_id": "owner_id",
            "hs_lead_status": "lead_status",
            "lifecyclestage": "lifecycle_stage",
            "createdate": "create_date",
            "lastmodifieddate": "last_modified_date",
            "lastactivitydate": "last_activity_date",
            "hs_object_id": "record_id",
            "website": "website",
        }
        if column_mapping:
            default_mapping.update(column_mapping)

        processed_count = 0
        for item in items:
            try:
                contact = self._dict_to_contact(item, default_mapping, id_key, property_key)
                if contact and contact.record_id:
                    self.contacts[contact.record_id] = contact
                    self._index_contact(contact)
                    processed_count += 1
            except Exception as e:
                logger.warning(f"Error processing JSON item: {e}")
                continue

        logger.info(f"Successfully processed {processed_count} contacts from JSON")
        return processed_count

    # ── Internal: build records ───────────────────────────────────────

    def _dict_to_contact(
        self,
        item: Dict,
        mapping: Dict,
        id_key: str = "id",
        property_key: str = "properties",
    ) -> Optional[ContactRecord]:
        record_id = str(item.get(id_key, ""))
        props = item.get(property_key, item) if property_key in item else item

        record_data: Dict = {"record_id": record_id}
        for src, canonical in mapping.items():
            if src in props and props[src] is not None and str(props[src]).strip() != "":
                record_data[canonical] = props[src]

        raw_data = {k: v for k, v in props.items() if k not in mapping and v is not None}
        valid_fields = {
            k: v
            for k, v in record_data.items()
            if k in ContactRecord.__dataclass_fields__ and k != "raw_data"
        }
        contact = ContactRecord(**valid_fields, raw_data=raw_data)
        self._normalize_contact(contact)
        self._calculate_quality_scores(contact)
        return contact

    def _row_to_contact(self, row: pd.Series, mapping: Dict) -> Optional[ContactRecord]:
        record_data = {}

        for csv_field, canonical_field in mapping.items():
            if csv_field in row and pd.notna(row[csv_field]):
                record_data[canonical_field] = row[csv_field]

        if 'record_id' not in record_data:
            record_data['record_id'] = (
                str(row.name) if hasattr(row, 'name') else self._generate_id(row)
            )

        raw_data = {}
        for fld, value in row.items():
            if fld not in mapping and pd.notna(value):
                raw_data[fld] = value

        contact = ContactRecord(**record_data, raw_data=raw_data)
        self._normalize_contact(contact)
        self._calculate_quality_scores(contact)
        return contact

    # ── Normalization ─────────────────────────────────────────────────

    def _normalize_contact(self, contact: ContactRecord):
        if contact.email:
            contact.email = contact.email.lower().strip()

        if contact.first_name:
            contact.first_name = self._normalize_name(contact.first_name)
        if contact.last_name:
            contact.last_name = self._normalize_name(contact.last_name)

        if contact.linkedin_url:
            contact.linkedin_url = self._normalize_linkedin_url(contact.linkedin_url)

        if contact.website and not contact.company_domain:
            contact.company_domain = self._extract_domain_from_url(contact.website)
        if contact.email and not contact.company_domain:
            domain = contact.email.split('@')[1] if '@' in contact.email else None
            personal_domains = (
                '.gmail.com', '.outlook.com', '.yahoo.com', '.hotmail.com',
                '.aol.com', '.icloud.com', '.me.com', '.live.com',
                '.msn.com', '.protonmail.com', '.mail.com',
            )
            if domain and not any(domain.endswith(d) for d in personal_domains):
                contact.company_domain = domain

    def _normalize_name(self, name: str) -> str:
        if not name:
            return ""
        return re.sub(r'[^\w\s]', '', name).strip().title()

    def _normalize_linkedin_url(self, url: str) -> str:
        if not url:
            return ""
        if 'linkedin.com/in/' in url.lower():
            match = re.search(r'linkedin\.com/in/([^/?]+)', url.lower())
            if match:
                return f"linkedin.com/in/{match.group(1)}"
        return url.lower().strip()

    def _extract_domain_from_url(self, url: str) -> Optional[str]:
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

    # ── Quality scores ────────────────────────────────────────────────

    def _calculate_quality_scores(self, contact: ContactRecord):
        key_fields = [
            contact.email, contact.first_name, contact.last_name,
            contact.company_name, contact.job_title, contact.linkedin_url,
        ]
        filled_fields = sum(1 for f in key_fields if f and str(f).strip())
        contact.completeness_score = filled_fields / len(key_fields)

        engagement_factors = []
        if contact.last_activity_date:
            engagement_factors.append(1.0)
        if contact.lead_status and contact.lead_status.upper() in [
            'CONNECTED', 'OPEN_DEAL', 'IN_PROGRESS'
        ]:
            engagement_factors.append(1.0)
        if contact.lifecycle_stage and contact.lifecycle_stage.upper() in [
            'CUSTOMER', 'OPPORTUNITY', 'SQL'
        ]:
            engagement_factors.append(1.0)

        contact.engagement_score = (
            float(np.mean(engagement_factors)) if engagement_factors else 0.0
        )
        contact.data_quality_score = (
            contact.completeness_score * 0.7 + contact.engagement_score * 0.3
        )

    # ── Indexing ──────────────────────────────────────────────────────

    def _index_contact(self, contact: ContactRecord):
        rid = contact.record_id

        if contact.email:
            self.email_index[contact.email].add(rid)

        if contact.linkedin_url:
            self.linkedin_index[contact.linkedin_url].add(rid)

        if contact.company_domain:
            self.domain_index[contact.company_domain].add(rid)

        name_key = self._block_key_name(contact)
        if name_key and contact.company_domain:
            self.name_domain_index[(name_key, contact.company_domain)].add(rid)

    def _block_key_name(self, contact: ContactRecord) -> Optional[str]:
        if not contact.last_name:
            return None
        last = contact.last_name.strip().lower()
        first = (contact.first_name or "").strip().lower()
        if not last:
            return None
        if first:
            return f"{last}_{first[0]}"
        return last

    def _generate_id(self, row: pd.Series) -> str:
        key_fields = []
        if pd.notna(row.get('email')):
            key_fields.append(str(row['email']))
        if pd.notna(row.get('firstname')):
            key_fields.append(str(row['firstname']))
        if pd.notna(row.get('lastname')):
            key_fields.append(str(row['lastname']))

        if key_fields:
            return hashlib.md5('|'.join(key_fields).encode()).hexdigest()[:12]
        return f"contact_{row.name}" if hasattr(row, 'name') else f"contact_{id(row)}"

    # ── Main dedup entry point ────────────────────────────────────────

    def find_duplicates(self) -> List[DuplicateMatch]:
        logger.info("Starting deduplication process...")
        matches = []

        # Step 1: Deterministic matching
        deterministic_matches = self._find_deterministic_matches()
        matches.extend(deterministic_matches)
        logger.info(f"Found {len(deterministic_matches)} deterministic matches")

        # Step 2: Probabilistic matching (excluding already matched pairs)
        matched_pairs: Set[Tuple[str, str]] = set()
        for m in deterministic_matches:
            pair = (min(m.contact_1_id, m.contact_2_id), max(m.contact_1_id, m.contact_2_id))
            matched_pairs.add(pair)

        probabilistic_matches = self._find_probabilistic_matches(exclude_pairs=matched_pairs)
        matches.extend(probabilistic_matches)
        logger.info(f"Found {len(probabilistic_matches)} probabilistic matches")

        # Step 3: Add survivor recommendations
        for match in matches:
            match.survivor_recommendation = self._recommend_survivor(
                match.contact_1_id, match.contact_2_id
            )

        logger.info(f"Total matches found: {len(matches)}")
        return matches

    # ── Deterministic matching ────────────────────────────────────────

    def _find_deterministic_matches(self) -> List[DuplicateMatch]:
        matches = []
        seen_pairs: Set[Tuple[str, str]] = set()

        def _canon_pair(a: str, b: str) -> Tuple[str, str]:
            return (min(a, b), max(a, b))

        # Email-based matching
        for email, contact_ids in self.email_index.items():
            if len(contact_ids) > 1:
                for id1, id2 in combinations(contact_ids, 2):
                    pair = _canon_pair(id1, id2)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    matches.append(DuplicateMatch(
                        contact_1_id=pair[0],
                        contact_2_id=pair[1],
                        match_type=MatchType.DETERMINISTIC_HIGH,
                        confidence_score=0.98,
                        matching_fields=['email'],
                        explanation=f"Exact email match: {email}",
                    ))

        # LinkedIn URL matching
        for linkedin, contact_ids in self.linkedin_index.items():
            if len(contact_ids) > 1:
                for id1, id2 in combinations(contact_ids, 2):
                    pair = _canon_pair(id1, id2)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    matches.append(DuplicateMatch(
                        contact_1_id=pair[0],
                        contact_2_id=pair[1],
                        match_type=MatchType.DETERMINISTIC_HIGH,
                        confidence_score=0.96,
                        matching_fields=['linkedin_url'],
                        explanation=f"Exact LinkedIn URL match: {linkedin}",
                    ))

        # Name + company domain (same person at same company, emails don't conflict)
        for (name_key, domain), contact_ids in self.name_domain_index.items():
            if len(contact_ids) > 1:
                for id1, id2 in combinations(contact_ids, 2):
                    pair = _canon_pair(id1, id2)
                    if pair in seen_pairs:
                        continue
                    c1, c2 = self.contacts[id1], self.contacts[id2]
                    # If both have email at DIFFERENT domains, they're at
                    # different orgs — skip.  Same-domain but different
                    # addresses (jane.doe@ vs jdoe@) is exactly the case
                    # we want to catch.
                    if c1.email and c2.email:
                        d1 = c1.email.split('@')[1] if '@' in c1.email else ''
                        d2 = c2.email.split('@')[1] if '@' in c2.email else ''
                        if d1 != d2:
                            continue
                    # Verify actual name similarity (block key is coarse)
                    name_sim = self._name_similarity(c1, c2)
                    if name_sim < 0.85:
                        continue
                    seen_pairs.add(pair)
                    matches.append(DuplicateMatch(
                        contact_1_id=pair[0],
                        contact_2_id=pair[1],
                        match_type=MatchType.DETERMINISTIC_MEDIUM,
                        confidence_score=0.88,
                        matching_fields=['first_name', 'last_name', 'company_domain'],
                        explanation=f"Same name + company domain: {name_key} @ {domain}",
                    ))

        return matches

    # ── Probabilistic matching ────────────────────────────────────────

    def _get_probabilistic_candidate_pairs(
        self, exclude_pairs: Set[Tuple[str, str]]
    ) -> Set[Tuple[str, str]]:
        contact_ids = list(self.contacts.keys())
        n = len(contact_ids)

        if self._use_blocking and n >= self._blocking_min_candidates:
            pairs: Set[Tuple[str, str]] = set()

            # Block by name key (last + first initial) — catches "John Smith" at
            # different companies / with different emails
            name_only_blocks: Dict[str, Set[str]] = defaultdict(set)
            for cid in contact_ids:
                c = self.contacts[cid]
                key = self._block_key_name(c)
                if key:
                    name_only_blocks[key].add(cid)

            for ids in name_only_blocks.values():
                ids_list = list(ids)
                if len(ids_list) < 2:
                    continue
                # Cap block size to avoid N^2 explosion on common last+initial
                max_in_block = 100
                capped = ids_list[:max_in_block]
                for i, id1 in enumerate(capped):
                    for id2 in capped[i + 1:]:
                        pair = (min(id1, id2), max(id1, id2))
                        pairs.add(pair)

            # Remove already-matched pairs
            pairs -= exclude_pairs
            return pairs
        else:
            pairs = set()
            for i, id1 in enumerate(contact_ids):
                for id2 in contact_ids[i + 1:]:
                    pair = (min(id1, id2), max(id1, id2))
                    if pair not in exclude_pairs:
                        pairs.add(pair)
            return pairs

    def _name_similarity(self, contact1: ContactRecord, contact2: ContactRecord) -> float:
        name1 = f"{contact1.first_name or ''} {contact1.last_name or ''}".strip()
        name2 = f"{contact2.first_name or ''} {contact2.last_name or ''}".strip()
        if not name1 or not name2:
            return 0.0
        return self._jaro_winkler_similarity(name1, name2)

    def _find_probabilistic_matches(
        self, exclude_pairs: Set[Tuple[str, str]]
    ) -> List[DuplicateMatch]:
        matches = []
        candidate_pairs = self._get_probabilistic_candidate_pairs(exclude_pairs)
        logger.info(f"Probabilistic candidates: {len(candidate_pairs)} pairs")

        for (id1, id2) in candidate_pairs:
            contact1 = self.contacts[id1]
            contact2 = self.contacts[id2]

            # Determine if emails are at different domains (cross-domain pair)
            cross_domain = False
            if contact1.email and contact2.email:
                d1 = contact1.email.split('@')[1] if '@' in contact1.email else ''
                d2 = contact2.email.split('@')[1] if '@' in contact2.email else ''
                if d1 and d2 and d1 != d2:
                    cross_domain = True

            # Require strong name agreement
            name_sim = self._name_similarity(contact1, contact2)
            if name_sim < self._min_name_similarity:
                continue

            # Cross-domain pairs (job changers): require near-exact name match
            # to avoid false positives on common names like "David Kim"
            if cross_domain and name_sim < self._cross_domain_min_name_similarity:
                continue

            # Calculate composite similarity + count contributing dimensions
            similarity_score, dimensions = self._calculate_similarity(contact1, contact2)

            # When contacts are sparse (only name matches, nothing else),
            # require a higher bar to avoid matching "John Smith" != "Jon Smith"
            # at unrelated companies
            if dimensions <= 1 and name_sim < self._sparse_min_name_similarity:
                continue

            # For cross-domain matches: the composite score will be low because
            # company/domain fields don't match.  Use name similarity directly
            # as the confidence signal instead — we already required a very
            # high name bar (0.95) to reach this point.
            if cross_domain:
                if name_sim >= self._cross_domain_min_name_similarity:
                    match = DuplicateMatch(
                        contact_1_id=id1,
                        contact_2_id=id2,
                        match_type=MatchType.PROBABILISTIC_MEDIUM,
                        confidence_score=round(name_sim * 0.85, 4),
                        matching_fields=self._get_matching_fields(contact1, contact2),
                        explanation=(
                            f"Same name across different organizations "
                            f"(name similarity {name_sim:.0%})"
                        ),
                    )
                    matches.append(match)
                continue  # skip normal scoring for cross-domain pairs

            match_type, explanation = self._classify_probabilistic_match(
                similarity_score, contact1, contact2
            )

            if match_type and similarity_score >= self.PROBABILISTIC_MEDIUM_THRESHOLD:
                match = DuplicateMatch(
                    contact_1_id=id1,
                    contact_2_id=id2,
                    match_type=match_type,
                    confidence_score=similarity_score,
                    matching_fields=self._get_matching_fields(contact1, contact2),
                    explanation=explanation,
                )
                matches.append(match)

        return matches

    def _calculate_similarity(
        self, contact1: ContactRecord, contact2: ContactRecord
    ) -> Tuple[float, int]:
        """Calculate similarity. Returns (score, dimension_count).

        Uses FIXED total weight so sparse contacts don't get inflated scores.
        """
        w = self._weights
        total_fixed_weight = sum(w.values())  # always the same denominator

        weighted_sum = 0.0
        dimensions = 0  # how many non-name fields contributed

        # Name (always evaluated)
        name1 = f"{contact1.first_name or ''} {contact1.last_name or ''}".strip()
        name2 = f"{contact2.first_name or ''} {contact2.last_name or ''}".strip()
        if name1 and name2:
            name_sim = self._jaro_winkler_similarity(name1, name2)
            weighted_sum += name_sim * w["name"]
        else:
            # No name to compare — can't produce a meaningful score
            return 0.0, 0

        # Company name
        if contact1.company_name and contact2.company_name:
            company_sim = self._jaro_winkler_similarity(
                contact1.company_name, contact2.company_name
            )
            weighted_sum += company_sim * w["company"]
            if company_sim > 0.7:
                dimensions += 1

        # Job title
        if contact1.job_title and contact2.job_title:
            title_sim = self._jaro_winkler_similarity(
                contact1.job_title, contact2.job_title
            )
            weighted_sum += title_sim * w["title"]
            if title_sim > 0.7:
                dimensions += 1

        # Company domain
        if contact1.company_domain and contact2.company_domain:
            domain_sim = 1.0 if contact1.company_domain == contact2.company_domain else 0.0
            weighted_sum += domain_sim * w["domain"]
            if domain_sim > 0.5:
                dimensions += 1

        score = weighted_sum / total_fixed_weight
        return min(score, 1.0), dimensions

    # ── String similarity ─────────────────────────────────────────────

    def _jaro_winkler_similarity(self, s1: str, s2: str) -> float:
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
        self, score: float, contact1: ContactRecord, contact2: ContactRecord
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

    def _get_matching_fields(
        self, contact1: ContactRecord, contact2: ContactRecord
    ) -> List[str]:
        matching = []

        if contact1.email and contact2.email and contact1.email == contact2.email:
            matching.append('email')

        if contact1.first_name and contact2.first_name:
            if self._jaro_winkler_similarity(contact1.first_name, contact2.first_name) > 0.8:
                matching.append('first_name')

        if contact1.last_name and contact2.last_name:
            if self._jaro_winkler_similarity(contact1.last_name, contact2.last_name) > 0.8:
                matching.append('last_name')

        if contact1.company_name and contact2.company_name:
            if self._jaro_winkler_similarity(contact1.company_name, contact2.company_name) > 0.7:
                matching.append('company_name')

        if contact1.company_domain and contact2.company_domain:
            if contact1.company_domain == contact2.company_domain:
                matching.append('company_domain')

        if contact1.job_title and contact2.job_title:
            if self._jaro_winkler_similarity(contact1.job_title, contact2.job_title) > 0.7:
                matching.append('job_title')

        return matching

    # ── Survivor selection ────────────────────────────────────────────

    def _recommend_survivor(self, id1: str, id2: str) -> str:
        contact1 = self.contacts[id1]
        contact2 = self.contacts[id2]
        score1 = self._calculate_survivor_score(contact1)
        score2 = self._calculate_survivor_score(contact2)
        return id1 if score1 >= score2 else id2

    def _calculate_survivor_score(self, contact: ContactRecord) -> float:
        score = 0.0

        # Data completeness (30%)
        score += contact.data_quality_score * 0.30

        # Recency of last activity — most recent wins (30%)
        # Parse the date and convert to a 0-1 scale based on how recent it is
        recency = 0.0
        if contact.last_activity_date:
            try:
                activity_dt = pd.to_datetime(contact.last_activity_date, utc=True)
                now = pd.Timestamp.now(tz='UTC')
                days_ago = (now - activity_dt).days
                # 0 days ago = 1.0, 365+ days ago = ~0.1
                recency = max(0.1, 1.0 - (days_ago / 400))
            except Exception:
                recency = 0.1  # has a date but can't parse it
        score += recency * 0.30

        # Lifecycle stage (20%)
        stage_scores = {
            'CUSTOMER': 1.0, 'OPPORTUNITY': 0.9, 'SQL': 0.8,
            'MQL': 0.7, 'LEAD': 0.5, 'SUBSCRIBER': 0.3,
        }
        if contact.lifecycle_stage:
            stage_score = stage_scores.get(contact.lifecycle_stage.upper(), 0.1)
            score += stage_score * 0.20

        # Has an owner (10%)
        if contact.owner_id and contact.owner_id != 'unassigned':
            score += 0.10

        # Has been modified recently (10%)
        mod_recency = 0.0
        if contact.last_modified_date:
            try:
                mod_dt = pd.to_datetime(contact.last_modified_date, utc=True)
                now = pd.Timestamp.now(tz='UTC')
                days_ago = (now - mod_dt).days
                mod_recency = max(0.1, 1.0 - (days_ago / 400))
            except Exception:
                mod_recency = 0.1
        score += mod_recency * 0.10

        return score

    # ── Clustering ────────────────────────────────────────────────────

    def create_clusters(self, matches: List[DuplicateMatch]) -> Dict[str, List[str]]:
        graph: Dict[str, Set[str]] = defaultdict(set)
        for match in matches:
            graph[match.contact_1_id].add(match.contact_2_id)
            graph[match.contact_2_id].add(match.contact_1_id)

        visited: Set[str] = set()
        clusters = {}
        cluster_id = 0

        for contact_id in graph:
            if contact_id not in visited:
                cluster = self._dfs_cluster(graph, contact_id, visited)
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
        total_contacts = len(self.contacts)
        total_matches = len(matches)
        total_clusters = len(clusters)
        contacts_in_clusters = sum(len(c) for c in clusters.values())
        duplicates_to_remove = contacts_in_clusters - total_clusters

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
                f"{match.contact_1_id}_{match.contact_2_id}"
            ] = action.value

        report = {
            'summary': {
                'total_contacts': total_contacts,
                'total_matches': total_matches,
                'total_clusters': total_clusters,
                'duplicates_to_remove': duplicates_to_remove,
                'deduplication_rate': (
                    (duplicates_to_remove / total_contacts * 100)
                    if total_contacts > 0
                    else 0
                ),
            },
            'match_breakdown': match_type_counts,
            'matches': [
                {
                    'contact_1_id': m.contact_1_id,
                    'contact_2_id': m.contact_2_id,
                    'match_type': m.match_type.value,
                    'confidence_score': round(m.confidence_score, 3),
                    'matching_fields': m.matching_fields,
                    'explanation': m.explanation,
                    'survivor_recommendation': m.survivor_recommendation,
                    'recommended_action': action_recommendations.get(
                        f"{m.contact_1_id}_{m.contact_2_id}",
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

        # Helper to serialize one contact for the UI
        def _contact_dict(c):
            return {
                "id": c.record_id,
                "name": f"{c.first_name or ''} {c.last_name or ''}".strip() or "\u2014",
                "email": c.email or "\u2014",
                "company": c.company_name or "\u2014",
                "phone": c.phone or "\u2014",
                "title": c.job_title or "\u2014",
                "lifecycle_stage": c.lifecycle_stage or "\u2014",
                "last_activity_date": c.last_activity_date or "\u2014",
                "last_modified_date": c.last_modified_date or "\u2014",
                "owner_id": c.owner_id or "\u2014",
                "survivor_score": round(self._calculate_survivor_score(c), 4),
                "data_quality_score": round(c.data_quality_score, 4),
            }

        # Enrich matches with contact details for UI
        enriched_matches = []
        for match in report["matches"]:
            m = dict(match)
            for key in ("contact_1_id", "contact_2_id"):
                cid = m.get(key)
                c = self.contacts.get(cid) or self.contacts.get(str(cid))
                prefix = "contact_1" if key == "contact_1_id" else "contact_2"
                if c:
                    m[f"{prefix}_name"] = (
                        f"{c.first_name or ''} {c.last_name or ''}".strip() or "\u2014"
                    )
                    m[f"{prefix}_email"] = c.email or "\u2014"
                    m[f"{prefix}_company"] = c.company_name or "\u2014"
                    m[f"{prefix}_phone"] = c.phone or "\u2014"
                    m[f"{prefix}_title"] = c.job_title or "\u2014"
                else:
                    m[f"{prefix}_name"] = "\u2014"
                    m[f"{prefix}_email"] = "\u2014"
                    m[f"{prefix}_company"] = "\u2014"
                    m[f"{prefix}_phone"] = "\u2014"
                    m[f"{prefix}_title"] = "\u2014"
            enriched_matches.append(m)

        # Build contacts dict for cluster view (only contacts involved in matches)
        contacts_in_clusters = set()
        for member_ids in report["clusters"].values():
            for mid in member_ids:
                contacts_in_clusters.add(mid)
                contacts_in_clusters.add(str(mid))

        contacts_dict = {}
        for cid in contacts_in_clusters:
            c = self.contacts.get(cid) or self.contacts.get(str(cid))
            if c and str(c.record_id) not in contacts_dict:
                contacts_dict[str(c.record_id)] = _contact_dict(c)

        report_for_json = {**report, "matches": enriched_matches, "contacts": contacts_dict}
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
            c1 = self.contacts.get(match['contact_1_id'])
            c2 = self.contacts.get(match['contact_2_id'])
            if not c1 or not c2:
                continue
            matches_data.append({
                'Contact_1_ID': match['contact_1_id'],
                'Contact_1_Name': f"{c1.first_name or ''} {c1.last_name or ''}".strip(),
                'Contact_1_Email': c1.email or '',
                'Contact_1_Company': c1.company_name or '',
                'Contact_2_ID': match['contact_2_id'],
                'Contact_2_Name': f"{c2.first_name or ''} {c2.last_name or ''}".strip(),
                'Contact_2_Email': c2.email or '',
                'Contact_2_Company': c2.company_name or '',
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
    use_json: bool = True,
    output_path: str = "deduplication_results",
    config: Optional[Dict] = None,
):
    """Run the Contact Deduplication Engine on a file (JSON or CSV)."""
    engine = ContactDeduplicationEngine(config=config)
    input_path = input_path or "contacts-last-activity-unknown.json"

    try:
        if use_json or (input_path and input_path.endswith(".json")):
            contact_count = engine.load_json(input_path)
        else:
            contact_count = engine.load_csv(input_path)
        logger.info(f"Loaded {contact_count} contacts")

        matches = engine.find_duplicates()
        clusters = engine.create_clusters(matches)
        report = engine.generate_report(matches, clusters)

        summary = report["summary"]
        print("\n=== DEDUPLICATION SUMMARY ===")
        print(f"Total Contacts: {summary['total_contacts']}")
        print(f"Potential Matches: {summary['total_matches']}")
        print(f"Duplicate Clusters: {summary['total_clusters']}")
        print(f"Duplicates to Remove: {summary['duplicates_to_remove']}")
        print(f"Deduplication Rate: {summary['deduplication_rate']:.2f}%")

        print("\n=== MATCH BREAKDOWN ===")
        for match_type, count in report["match_breakdown"].items():
            if count > 0:
                print(f"  {match_type}: {count}")

        json_path, csv_path = engine.export_results(report, output_path)
        print(f"\nResults exported to: {json_path}, {csv_path}")
        return report
    except FileNotFoundError:
        logger.error(
            f"File not found: {input_path}. Provide a path to a CSV or JSON contacts file."
        )
        return None
    except Exception as e:
        logger.error(f"Error in deduplication process: {e}")
        raise


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    use_json = path is None or path.endswith(".json")
    main(input_path=path, use_json=use_json)
