"""
Adapt ContactDeduplicationEngine output to normalized shape: entities, matches, clusters
with external_id (record_id) keys and reasons_json as list of { feature, weight, detail }.
"""
import json
from typing import Any

# ContactRecord is a dataclass; we build a serializable dict for raw_json
def _contact_to_raw_json(contact: Any) -> dict:
    """Build a JSON-serializable dict from a ContactRecord."""
    out = {
        "id": contact.record_id,
        "record_id": contact.record_id,
        "first_name": getattr(contact, "first_name", None),
        "last_name": getattr(contact, "last_name", None),
        "email": getattr(contact, "email", None),
        "phone": getattr(contact, "phone", None),
        "company_name": getattr(contact, "company_name", None),
        "job_title": getattr(contact, "job_title", None),
        "linkedin_url": getattr(contact, "linkedin_url", None),
        "website": getattr(contact, "website", None),
        "company_domain": getattr(contact, "company_domain", None),
        "owner_id": getattr(contact, "owner_id", None),
        "lead_status": getattr(contact, "lead_status", None),
        "lifecycle_stage": getattr(contact, "lifecycle_stage", None),
        "create_date": getattr(contact, "create_date", None),
        "last_modified_date": getattr(contact, "last_modified_date", None),
        "last_activity_date": getattr(contact, "last_activity_date", None),
    }
    # Coerce to native types for JSON
    for k, v in list(out.items()):
        if hasattr(v, "item"):  # numpy scalar
            out[k] = v.item() if hasattr(v, "item") else float(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat() if v else None
    raw = getattr(contact, "raw_data", None) or {}
    for k, v in raw.items():
        if k not in out and v is not None:
            if hasattr(v, "item"):
                out[k] = v.item()
            elif hasattr(v, "isoformat"):
                out[k] = v.isoformat()
            else:
                try:
                    json.dumps(v)
                    out[k] = v
                except (TypeError, ValueError):
                    out[k] = str(v)
    return out


def _match_to_reasons(matching_fields: list, explanation: str) -> list[dict]:
    """Build reasons_json from matching_fields and explanation."""
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


def adapt_contact_engine(engine: Any) -> dict:
    """
    Given a loaded ContactDeduplicationEngine (after load_csv + find_duplicates + create_clusters),
    return normalized result with external_id keys.
    """
    matches = engine.find_duplicates()
    clusters_dict = engine.create_clusters(matches)

    entities = []
    for record_id, contact in engine.contacts.items():
        entities.append({
            "external_id": str(record_id),
            "raw_json": _contact_to_raw_json(contact),
        })

    matches_out = []
    for m in matches:
        reasons = _match_to_reasons(
            getattr(m, "matching_fields", []) or [],
            getattr(m, "explanation", "") or "",
        )
        survivor = getattr(m, "survivor_recommendation", None)
        matches_out.append({
            "a_external_id": getattr(m, "contact_1_id", None),
            "b_external_id": getattr(m, "contact_2_id", None),
            "score": float(getattr(m, "confidence_score", 0)),
            "reasons_json": reasons,
            "recommended_survivor_external_id": str(survivor) if survivor else None,
        })

    clusters_out = []
    for cluster_key, member_ids in clusters_dict.items():
        member_external_ids = [str(x) for x in member_ids]
        # Use engine's survivor recommendation for the first pair or compute per cluster
        recommended = None
        if member_external_ids and len(member_external_ids) >= 2:
            # Engine has _recommend_survivor(id1, id2); for cluster pick from first two then compare with rest
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
