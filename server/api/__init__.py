from fastapi import APIRouter
from . import runs, matches, clusters, export

api_router = APIRouter()
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(matches.router, prefix="/runs", tags=["matches"])
api_router.include_router(clusters.router, prefix="/runs", tags=["clusters"])
api_router.include_router(export.router, prefix="/runs", tags=["export"])
