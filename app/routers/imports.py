from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services.assets import import_assets

router = APIRouter(prefix="/api", tags=["import"])


@router.post("/import")
def import_endpoint(
    assets: List[schemas.AssetImport],
    db: Session = Depends(get_db),
):
    return import_assets(db, assets)
