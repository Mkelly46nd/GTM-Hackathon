from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ----- Runs -----
class RunCreate(BaseModel):
    entity_type: str  # contact | company
    # file via multipart
    params: Optional[str] = None  # JSON string


class RunResponse(BaseModel):
    id: str
    entity_type: str
    source_type: str
    created_at: datetime
    params_json: Optional[str]
    status: str

    class Config:
        from_attributes = True


class RunDetailResponse(RunResponse):
    total_entities: int = 0
    total_matches: int = 0
    matches_high: int = 0  # >= 0.95
    matches_medium: int = 0  # 0.85 - 0.95
    matches_low: int = 0  # < 0.85
    total_clusters: int = 0


# ----- Entities -----
class EntityResponse(BaseModel):
    id: str
    run_id: str
    entity_type: str
    external_id: str
    raw_json: Optional[dict] = None

    class Config:
        from_attributes = True


# ----- Matches -----
class ReasonItem(BaseModel):
    feature: str
    weight: float
    detail: str


class MatchResponse(BaseModel):
    id: str
    run_id: str
    entity_type: str
    a_entity_id: str
    b_entity_id: str
    score: float
    reasons_json: Optional[list] = None  # list of ReasonItem
    recommended_survivor_entity_id: Optional[str]
    status: str
    updated_at: datetime
    # Optional expanded for UI
    entity_a: Optional[EntityResponse] = None
    entity_b: Optional[EntityResponse] = None

    class Config:
        from_attributes = True


class MatchesListResponse(BaseModel):
    items: list[MatchResponse]
    total: int
    limit: int
    offset: int


class ApproveRejectBody(BaseModel):
    pass  # no body required


# ----- Clusters -----
class ClusterSummaryResponse(BaseModel):
    id: str
    run_id: str
    entity_type: str
    member_count: int
    member_entity_ids: list[str]
    recommended_survivor_entity_id: Optional[str]
    # Optional for list view
    recommended_survivor_name: Optional[str] = None

    class Config:
        from_attributes = True


class ClusterDetailResponse(BaseModel):
    id: str
    run_id: str
    entity_type: str
    member_entity_ids: list[str]
    recommended_survivor_entity_id: Optional[str]
    members: list[EntityResponse] = []
    pairwise_matches: list[MatchResponse] = []
    # field diff: list of { field_name, values: [val_a, val_b, ...] } per member

    class Config:
        from_attributes = True


# ----- Export -----
class ExportCsvBody(BaseModel):
    selection: str = "approved_survivors"


class ExportClayBody(BaseModel):
    approved_survivors: bool = True
    entity_ids: Optional[list[str]] = None  # optional explicit list


class ExportN8nBody(BaseModel):
    approved_survivors: bool = True
    entity_ids: Optional[list[str]] = None
