from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services.relationships import get_asset_relationships

router = APIRouter(prefix="/api", tags=["relationships"])


@router.get(
    "/assets/{asset_id}/relationships",
    response_model=schemas.AssetRelationshipsResponse,
)
def asset_relationships_endpoint(
    asset_id: str,
    db: Session = Depends(get_db),
):
    return get_asset_relationships(db, asset_id)
