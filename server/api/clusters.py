import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.models import Run, Match, Cluster, Entity
from server.schemas import ClusterSummaryResponse, ClusterDetailResponse, MatchResponse, EntityResponse

router = APIRouter()


def _entity_response(e: Entity) -> EntityResponse:
    raw = json.loads(e.raw_json) if e.raw_json else None
    return EntityResponse(id=e.id, run_id=e.run_id, entity_type=e.entity_type, external_id=e.external_id, raw_json=raw)


@router.get("/{run_id}/clusters", response_model=list[ClusterSummaryResponse])
def get_clusters(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    clusters = db.query(Cluster).filter(Cluster.run_id == run_id).all()
    result = []
    for c in clusters:
        member_ids = json.loads(c.member_entity_ids_json or "[]")
        rec_name = None
        if c.recommended_survivor_entity_id:
            rec_ent = db.query(Entity).filter(Entity.id == c.recommended_survivor_entity_id).first()
            if rec_ent and rec_ent.raw_json:
                raw = json.loads(rec_ent.raw_json)
                if run.entity_type == "contact":
                    rec_name = (raw.get("first_name") or "") + " " + (raw.get("last_name") or "")
                else:
                    rec_name = raw.get("name") or raw.get("domain") or rec_ent.external_id
                rec_name = (rec_name or "").strip() or rec_ent.external_id
        result.append(ClusterSummaryResponse(
            id=c.id,
            run_id=c.run_id,
            entity_type=c.entity_type,
            member_count=len(member_ids),
            member_entity_ids=member_ids,
            recommended_survivor_entity_id=c.recommended_survivor_entity_id,
            recommended_survivor_name=rec_name,
        ))
    return result


@router.get("/{run_id}/clusters/{cluster_id}", response_model=ClusterDetailResponse)
def get_cluster(run_id: str, cluster_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    c = db.query(Cluster).filter(Cluster.id == cluster_id, Cluster.run_id == run_id).first()
    if not c:
        raise HTTPException(404, "Cluster not found")

    member_ids = json.loads(c.member_entity_ids_json or "[]")
    members = []
    for eid in member_ids:
        e = db.query(Entity).filter(Entity.id == eid).first()
        if e:
            members.append(_entity_response(e))

    # Pairwise matches in this cluster (both a and b in member_ids)
    member_set = set(member_ids)
    match_rows = db.query(Match).filter(Match.run_id == run_id).all()
    pairwise = []
    for m in match_rows:
        if m.a_entity_id in member_set and m.b_entity_id in member_set:
            reasons = json.loads(m.reasons_json) if m.reasons_json else []
            pairwise.append(MatchResponse(
                id=m.id, run_id=m.run_id, entity_type=m.entity_type,
                a_entity_id=m.a_entity_id, b_entity_id=m.b_entity_id,
                score=m.score, reasons_json=reasons,
                recommended_survivor_entity_id=m.recommended_survivor_entity_id,
                status=m.status, updated_at=m.updated_at,
            ))

    return ClusterDetailResponse(
        id=c.id,
        run_id=c.run_id,
        entity_type=c.entity_type,
        member_entity_ids=member_ids,
        recommended_survivor_entity_id=c.recommended_survivor_entity_id,
        members=members,
        pairwise_matches=pairwise,
    )


@router.post("/{run_id}/clusters/{cluster_id}/approve")
def approve_cluster(run_id: str, cluster_id: str, db: Session = Depends(get_db)):
    c = db.query(Cluster).filter(Cluster.id == cluster_id, Cluster.run_id == run_id).first()
    if not c:
        raise HTTPException(404, "Cluster not found")
    member_ids = json.loads(c.member_entity_ids_json or "[]")
    member_set = set(member_ids)
    matches = db.query(Match).filter(Match.run_id == run_id).all()
    for m in matches:
        if m.a_entity_id in member_set and m.b_entity_id in member_set:
            m.status = "approved"
    db.commit()
    return {"status": "approved", "matches_updated": sum(1 for m in matches if m.a_entity_id in member_set and m.b_entity_id in member_set)}
