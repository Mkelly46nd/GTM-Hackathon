import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from server.database import get_db
from server.models import Run, Entity, Match, Cluster
from server.schemas import RunResponse, RunDetailResponse
from server.services.run_service import create_run

router = APIRouter()


@router.post("", response_model=RunResponse, status_code=201)
def post_runs(
    entity_type: str = Form(...),
    file: UploadFile = File(...),
    params: str | None = Form(None),
    db: Session = Depends(get_db),
):
    # Input is CSV only; we do not accept JSON or other formats for run data.
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file. Only CSV is supported for run input.")
    run = create_run(db, entity_type, file.file, params)
    return run


@router.get("", response_model=list[RunResponse])
def get_runs(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    runs = db.query(Run).order_by(Run.created_at.desc()).offset(offset).limit(limit).all()
    return runs


@router.get("/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    total_entities = db.query(Entity).filter(Entity.run_id == run_id).count()
    matches = db.query(Match).filter(Match.run_id == run_id).all()
    total_matches = len(matches)
    matches_high = sum(1 for m in matches if m.score >= 0.95)
    matches_medium = sum(1 for m in matches if 0.85 <= m.score < 0.95)
    matches_low = sum(1 for m in matches if m.score < 0.85)
    total_clusters = db.query(Cluster).filter(Cluster.run_id == run_id).count()

    return RunDetailResponse(
        id=run.id,
        entity_type=run.entity_type,
        source_type=run.source_type,
        created_at=run.created_at,
        params_json=run.params_json,
        status=run.status,
        total_entities=total_entities,
        total_matches=total_matches,
        matches_high=matches_high,
        matches_medium=matches_medium,
        matches_low=matches_low,
        total_clusters=total_clusters,
    )
