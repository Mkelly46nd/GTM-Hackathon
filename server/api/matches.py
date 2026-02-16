import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db
from server.models import Run, Match, Entity
from server.schemas import MatchResponse, MatchesListResponse, EntityResponse

router = APIRouter()


def _match_to_response(m: Match, db: Session, include_entities: bool = False) -> MatchResponse:
    reasons = []
    if m.reasons_json:
        try:
            reasons = json.loads(m.reasons_json)
        except Exception:
            pass
    out = MatchResponse(
        id=m.id,
        run_id=m.run_id,
        entity_type=m.entity_type,
        a_entity_id=m.a_entity_id,
        b_entity_id=m.b_entity_id,
        score=m.score,
        reasons_json=reasons,
        recommended_survivor_entity_id=m.recommended_survivor_entity_id,
        status=m.status,
        updated_at=m.updated_at,
    )
    if include_entities:
        ea = db.query(Entity).filter(Entity.id == m.a_entity_id).first()
        eb = db.query(Entity).filter(Entity.id == m.b_entity_id).first()
        out.entity_a = EntityResponse(
            id=ea.id, run_id=ea.run_id, entity_type=ea.entity_type, external_id=ea.external_id,
            raw_json=json.loads(ea.raw_json) if ea.raw_json else None,
        ) if ea else None
        out.entity_b = EntityResponse(
            id=eb.id, run_id=eb.run_id, entity_type=eb.entity_type, external_id=eb.external_id,
            raw_json=json.loads(eb.raw_json) if eb.raw_json else None,
        ) if eb else None
    return out


@router.get("/{run_id}/matches", response_model=MatchesListResponse)
def get_matches(
    run_id: str,
    min_score: float | None = Query(None),
    max_score: float | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    q = db.query(Match).filter(Match.run_id == run_id)
    if min_score is not None:
        q = q.filter(Match.score >= min_score)
    if max_score is not None:
        q = q.filter(Match.score <= max_score)
    if status is not None:
        q = q.filter(Match.status == status)

    total = q.count()
    items = q.order_by(Match.score.desc()).offset(offset).limit(limit).all()
    return MatchesListResponse(
        items=[_match_to_response(m, db, include_entities=True) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{run_id}/matches/{match_id}/approve")
def approve_match(run_id: str, match_id: str, db: Session = Depends(get_db)):
    m = db.query(Match).filter(Match.id == match_id, Match.run_id == run_id).first()
    if not m:
        raise HTTPException(404, "Match not found")
    m.status = "approved"
    db.commit()
    return {"status": "approved"}


@router.post("/{run_id}/matches/{match_id}/reject")
def reject_match(run_id: str, match_id: str, db: Session = Depends(get_db)):
    m = db.query(Match).filter(Match.id == match_id, Match.run_id == run_id).first()
    if not m:
        raise HTTPException(404, "Match not found")
    m.status = "rejected"
    db.commit()
    return {"status": "rejected"}
