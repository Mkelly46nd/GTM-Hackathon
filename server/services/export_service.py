import csv
import io
import json
from typing import Any

from sqlalchemy.orm import Session

from server.models import Run, Entity, Match, Cluster, Action
from server.config import settings


def _approved_survivor_entity_ids(db: Session, run_id: str) -> list[str]:
    """
    Entity IDs that are recommended survivors of at least one approved match
    (or are the cluster recommended survivor in an approved cluster).
    """
    approved_matches = db.query(Match).filter(
        Match.run_id == run_id,
        Match.status == "approved",
    ).all()
    survivor_ids = {m.recommended_survivor_entity_id for m in approved_matches if m.recommended_survivor_entity_id}
    # Also consider clusters where all matches are approved: their recommended survivor counts
    clusters = db.query(Cluster).filter(Cluster.run_id == run_id).all()
    for c in clusters:
        member_ids = json.loads(c.member_entity_ids_json or "[]")
        if not member_ids:
            continue
        match_count = db.query(Match).filter(
            Match.run_id == run_id,
            Match.status == "approved",
            ((Match.a_entity_id.in_(member_ids)) & (Match.b_entity_id.in_(member_ids))),
        ).count()
        # If this cluster has any approved match, include its recommended survivor
        if match_count > 0 and c.recommended_survivor_entity_id:
            survivor_ids.add(c.recommended_survivor_entity_id)
    return list(survivor_ids)


def export_csv(db: Session, run_id: str, selection: str = "approved_survivors") -> tuple[bytes, str]:
    """
    Build CSV bytes and suggested filename. selection strategy: approved_survivors.
    Logs an Action.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError("Run not found")

    if selection != "approved_survivors":
        raise ValueError("Only selection=approved_survivors is supported")

    survivor_ids = _approved_survivor_entity_ids(db, run_id)
    entities = db.query(Entity).filter(Entity.run_id == run_id, Entity.id.in_(survivor_ids)).all() if survivor_ids else []

    rows: list[dict[str, Any]] = []
    for e in entities:
        raw = json.loads(e.raw_json) if e.raw_json else {}
        raw["entity_id"] = e.id
        raw["external_id"] = e.external_id
        rows.append(raw)

    if not rows:
        # Empty CSV with minimal headers
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=["entity_id", "external_id"])
        w.writeheader()
        buf = out.getvalue().encode("utf-8")
    else:
        all_keys = set()
        for r in rows:
            all_keys.update(r.keys())
        fieldnames = ["entity_id", "external_id"] + sorted(k for k in all_keys if k not in ("entity_id", "external_id"))
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        buf = out.getvalue().encode("utf-8")

    action = Action(
        run_id=run_id,
        actor="local",
        action_type="export_csv",
        payload_json=json.dumps({"selection": selection, "count": len(entities)}),
    )
    db.add(action)
    db.commit()

    filename = f"dedup_export_{run.entity_type}_{run_id[:8]}.csv"
    return buf, filename


def export_clay(db: Session, run_id: str, approved_survivors: bool = True, entity_ids: list[str] | None = None) -> dict:
    """
    POST to CLAY_WEBHOOK_URL with payload. Returns response info or raises if URL not set.
    Logs an Action.
    """
    if not settings.clay_webhook_url:
        raise ValueError("CLAY_WEBHOOK_URL is not configured")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError("Run not found")

    if approved_survivors or not entity_ids:
        ids = _approved_survivor_entity_ids(db, run_id)
    else:
        ids = entity_ids

    entities = db.query(Entity).filter(Entity.run_id == run_id, Entity.id.in_(ids)).all() if ids else []
    payload = {
        "run_id": run_id,
        "entity_type": run.entity_type,
        "survivor_entity_ids": [e.id for e in entities],
        "entities": [json.loads(e.raw_json) if e.raw_json else {} for e in entities],
    }

    import urllib.request
    req = urllib.request.Request(
        settings.clay_webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")

    action = Action(
        run_id=run_id,
        actor="local",
        action_type="export_clay",
        payload_json=json.dumps({"count": len(entities), "response_status": getattr(resp, "status", 200)}),
    )
    db.add(action)
    db.commit()

    return {"status": "ok", "count": len(entities), "response_body": body[:500]}


def export_n8n(db: Session, run_id: str, approved_survivors: bool = True, entity_ids: list[str] | None = None) -> dict:
    """
    POST to N8N_WEBHOOK_URL. Logs an Action.
    """
    if not settings.n8n_webhook_url:
        raise ValueError("N8N_WEBHOOK_URL is not configured")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError("Run not found")

    if approved_survivors or not entity_ids:
        ids = _approved_survivor_entity_ids(db, run_id)
    else:
        ids = entity_ids

    entities = db.query(Entity).filter(Entity.run_id == run_id, Entity.id.in_(ids)).all() if ids else []
    payload = {
        "run_id": run_id,
        "entity_type": run.entity_type,
        "survivor_entity_ids": [e.id for e in entities],
        "entities": [json.loads(e.raw_json) if e.raw_json else {} for e in entities],
    }

    import urllib.request
    req = urllib.request.Request(
        settings.n8n_webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")

    action = Action(
        run_id=run_id,
        actor="local",
        action_type="trigger_n8n",
        payload_json=json.dumps({"count": len(entities), "response_status": getattr(resp, "status", 200)}),
    )
    db.add(action)
    db.commit()

    return {"status": "ok", "count": len(entities), "response_body": body[:500]}
