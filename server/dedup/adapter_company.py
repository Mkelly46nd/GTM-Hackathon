"""
Adapt CompanyDeduplicationEngine output to normalized shape: entities, matches, clusters
with external_id (record_id) keys and reasons_json.
"""
import json
from typing import Any

def _company_to_raw_json(company: Any) -> dict:
    """Build a JSON-serializable dict from a CompanyRecord."""
    all_domains = getattr(company, "all_domains", None)
    domains_list = list(all_domains) if all_domains is not None else []
    out = {
        "id": company.record_id,
        "record_id": company.record_id,
        "name": getattr(company, "name", None),
        "domain": getattr(company, "domain", None),
        "website": getattr(company, "website", None),
        "phone": getattr(company, "phone", None),
        "linkedin_url": getattr(company, "linkedin_url", None),
        "address": getattr(company, "address", None),
        "city": getattr(company, "city", None),
        "state": getattr(company, "state", None),
        "zip_code": getattr(company, "zip_code", None),
        "country": getattr(company, "country", None),
        "industry": getattr(company, "industry", None),
        "employee_count": getattr(company, "employee_count", None),
        "owner_id": getattr(company, "owner_id", None),
        "lead_status": getattr(company, "lead_status", None),
        "lifecycle_stage": getattr(company, "lifecycle_stage", None),
        "create_date": getattr(company, "create_date", None),
        "last_modified_date": getattr(company, "last_modified_date", None),
        "last_activity_date": getattr(company, "last_activity_date", None),
        "num_associated_contacts": getattr(company, "num_associated_contacts", None),
        "num_associated_deals": getattr(company, "num_associated_deals", None),
        "additional_domains": domains_list,
    }
    for k, v in list(out.items()):
        if hasattr(v, "item"):
            out[k] = v.item()
        elif hasattr(v, "isoformat") and v is not None:
            out[k] = v.isoformat()
    raw = getattr(company, "raw_data", None) or {}
    for k, v in raw.items():
        if k not in out and v is not None:
            try:
                json.dumps(v)
                out[k] = v
            except (TypeError, ValueError):
                out[k] = str(v)
    return out


def _match_to_reasons(matching_fields: list, explanation: str) -> list[dict]:
    reasons = []
    for i, field in enumerate(matching_fields or []):
        reasons.append({
            "feature": field,
            "weight": 1.0,
            "detail": explanation if i == 0 else f"matched on {field}",
        })
    if not reasons and explanation:
        reasons.append({"feature": "composite", "weight": 1.0, "detail": explanation})
    return reasons


def adapt_company_engine(engine: Any) -> dict:
    """
    Given a loaded CompanyDeduplicationEngine, return normalized result with external_id keys.
    """
    matches = engine.find_duplicates()
    clusters_dict = engine.create_clusters(matches)

    entities = []
    for record_id, company in engine.companies.items():
        entities.append({
            "external_id": str(record_id),
            "raw_json": _company_to_raw_json(company),
        })

    matches_out = []
    for m in matches:
        reasons = _match_to_reasons(
            getattr(m, "matching_fields", []) or [],
            getattr(m, "explanation", "") or "",
        )
        survivor = getattr(m, "survivor_recommendation", None)
        matches_out.append({
            "a_external_id": getattr(m, "company_1_id", None),
            "b_external_id": getattr(m, "company_2_id", None),
            "score": float(getattr(m, "confidence_score", 0)),
            "reasons_json": reasons,
            "recommended_survivor_external_id": str(survivor) if survivor else None,
        })

    clusters_out = []
    for cluster_key, member_ids in clusters_dict.items():
        member_external_ids = [str(x) for x in member_ids]
        recommended = None
        if member_external_ids and len(member_external_ids) >= 2:
            recommended = engine._recommend_survivor(member_ids[0], member_ids[1])
            for eid in member_ids[2:]:
                recommended = engine._recommend_survivor(recommended, eid)
        elif member_external_ids:
            recommended = member_external_ids[0]
        clusters_out.append({
            "cluster_key": cluster_key,
            "member_external_ids": member_external_ids,
            "recommended_survivor_external_id": str(recommended) if recommended else None,
        })

    return {
        "entities": entities,
        "matches": matches_out,
        "clusters": clusters_out,
    }
