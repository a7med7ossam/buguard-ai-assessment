from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.assets import merge_ai_enrichment
from app.ai import enrichment, risk, report, nl_query

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.post("/enrich")
def enrich_asset_endpoint(
    request: schemas.AnalyzeRequest,
    db: Session = Depends(get_db),
):
    asset = (
        db.query(models.Asset)
        .filter(models.Asset.id == request.asset_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset_dict = {
        "id": asset.id,
        "type": asset.type,
        "value": asset.value,
        "status": asset.status,
        "tags": asset.tags,
        "metadata": asset.metadata_,
    }

    result = enrichment.enrich_asset(asset_dict)

    merge_ai_enrichment(asset, result)
    db.commit()
    db.refresh(asset)

    return {"asset_id": asset.id, "enrichment": result}


@router.post("/risk")
def risk_score_endpoint(
    request: schemas.AnalyzeRequest,
    db: Session = Depends(get_db),
):
    asset = (
        db.query(models.Asset)
        .filter(models.Asset.id == request.asset_id)
        .first()
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset_dict = {
        "id": asset.id,
        "type": asset.type,
        "value": asset.value,
        "status": asset.status,
        "metadata": asset.metadata_,
    }

    risk_assessment = risk.evaluate_risk(asset_dict)
    return {"asset_id": asset.id, "risk_assessment": risk_assessment}


@router.get("/report", response_class=Response)
def generate_inventory_report(db: Session = Depends(get_db)):
    assets = db.query(models.Asset).all()

    asset_list = [
        {
            "type": a.type,
            "value": a.value,
            "status": a.status,
            "tags": a.tags,
            "metadata": a.metadata_,
        }
        for a in assets
    ]

    report_md = report.generate_report(asset_list)

    return Response(content=report_md, media_type="text/markdown")


@router.post("/query")
def natural_language_query(request: schemas.NLQueryRequest):
    if not request.query or not request.query.strip():
        return {"error": "Query cannot be empty"}

    try:
        result = nl_query.nl_asset_query(request.query)
        return {"query": request.query, **result}

    except Exception as e:
        return {
            "query": request.query,
            "error": str(e),
            "type": "error",
        }
