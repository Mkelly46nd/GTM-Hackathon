"""
Run deduplication engine from a CSV file and return normalized entities, matches, clusters.
Input is CSV only (no JSON). Uses repo root to import the contact/company engines.
"""
import sys
from pathlib import Path
from typing import Any

# Ensure repo root is on path so we can import the engines
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def run_dedup(entity_type: str, csv_path: str, params: dict | None = None) -> dict:
    """
    Run the appropriate engine on the CSV file at csv_path (CSV only; no JSON). Returns:
      entities: [ { external_id, raw_json }, ... ]
      matches: [ { a_external_id, b_external_id, score, reasons_json, recommended_survivor_external_id }, ... ]
      clusters: [ { cluster_key, member_external_ids, recommended_survivor_external_id }, ... ]
    """
    params = params or {}
    config = params.get("config")  # optional engine config

    if entity_type == "contact":
        from contact_deduplication_engine import ContactDeduplicationEngine
        from server.dedup.adapter_contact import adapt_contact_engine

        engine = ContactDeduplicationEngine(config=config)
        engine.load_csv(csv_path)
        return adapt_contact_engine(engine)

    elif entity_type == "company":
        from company_deduplication_engine import CompanyDeduplicationEngine
        from server.dedup.adapter_company import adapt_company_engine

        engine = CompanyDeduplicationEngine(config=config)
        engine.load_csv(csv_path)
        return adapt_company_engine(engine)

    else:
        raise ValueError(f"entity_type must be 'contact' or 'company', got {entity_type!r}")
