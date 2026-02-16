from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ExportCsvBody, ExportClayBody, ExportN8nBody
from server.services.export_service import export_csv, export_clay, export_n8n

router = APIRouter()


@router.post("/{run_id}/export/csv")
def post_export_csv(run_id: str, body: ExportCsvBody, db: Session = Depends(get_db)):
    try:
        buf, filename = export_csv(db, run_id, selection=body.selection)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(
        content=buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{run_id}/export/clay")
def post_export_clay(run_id: str, body: ExportClayBody, db: Session = Depends(get_db)):
    try:
        result = export_clay(db, run_id, approved_survivors=body.approved_survivors, entity_ids=body.entity_ids)
    except ValueError as e:
        raise HTTPException(503 if "not configured" in str(e) else 400, str(e))
    return result


@router.post("/{run_id}/export/n8n")
def post_export_n8n(run_id: str, body: ExportN8nBody, db: Session = Depends(get_db)):
    try:
        result = export_n8n(db, run_id, approved_survivors=body.approved_survivors, entity_ids=body.entity_ids)
    except ValueError as e:
        raise HTTPException(503 if "not configured" in str(e) else 400, str(e))
    return result
