"""
MVP survivor heuristic: choose entity with most non-empty whitelist fields,
then break ties by most recent last_modified_date / updated_at.
"""
from datetime import datetime
from typing import Any

# Whitelist of keys that count toward "completeness" for contacts
CONTACT_WHITELIST = {"email", "first_name", "last_name", "company_name", "phone", "job_title", "linkedin_url"}

# For companies
COMPANY_WHITELIST = {"name", "domain", "phone", "city", "state", "country", "industry", "linkedin_url"}


def _parse_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if hasattr(raw, "year"):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def pick_survivor_among_entity_dicts(
    entity_ids: list[str],
    raw_jsons_by_id: dict[str, dict],
    entity_type: str,
) -> str | None:
    """
    Given list of entity ids and a map id -> raw_json, return the id that should
    be the survivor (most complete, then most recent).
    """
    if not entity_ids:
        return None
    if len(entity_ids) == 1:
        return entity_ids[0]

    whitelist = CONTACT_WHITELIST if entity_type == "contact" else COMPANY_WHITELIST

    def score(eid: str) -> tuple[int, float]:
        raw = raw_jsons_by_id.get(eid) or {}
        filled = sum(1 for k in whitelist if raw.get(k) not in (None, "", "\u2014"))
        date_raw = raw.get("last_modified_date") or raw.get("last_activity_date") or raw.get("create_date")
        dt = _parse_date(date_raw)
        recency = dt.timestamp() if dt else 0.0
        return (filled, recency)

    return max(entity_ids, key=score)
