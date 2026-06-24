from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import datetime

import models
import schemas
from database import engine, get_db

import ai_layer
from pydantic import BaseModel

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Buguard Asset Management API")


@app.post("/api/import")
def import_assets(assets: List[schemas.AssetImport], db: Session = Depends(get_db)):
    imported_count = 0
    updated_count = 0
    skipped_count = 0

    for asset_data in assets:
        try:
            # 1. Check if asset exists (DEDUP by type + value)
            existing_asset = db.query(models.Asset).filter(
                models.Asset.type == asset_data.type,
                models.Asset.value == asset_data.value
            ).first()

            # -------------------------------
            # EXISTING ASSET
            # -------------------------------
            if existing_asset:
                existing_asset.last_seen = datetime.datetime.utcnow()
                existing_asset.status = "active"

                # Merge tags
                combined_tags = set(existing_asset.tags or [])
                combined_tags.update(asset_data.tags or [])
                existing_asset.tags = list(combined_tags)

                # Merge metadata
                current_metadata = existing_asset.metadata_ or {}
                new_metadata = asset_data.metadata or {}
                existing_asset.metadata_ = {**current_metadata, **new_metadata}

                asset_obj = existing_asset
                updated_count += 1

            # -------------------------------
            # NEW ASSET
            # -------------------------------
            else:
                new_asset = models.Asset(
                    id=asset_data.id,
                    type=asset_data.type,
                    value=asset_data.value,
                    status=asset_data.status,
                    first_seen=datetime.datetime.utcnow(),
                    last_seen=datetime.datetime.utcnow(),
                    source=asset_data.source,
                    tags=asset_data.tags,
                    metadata_=asset_data.metadata
                )
                db.add(new_asset)
                db.flush()
                
                asset_obj = new_asset
                imported_count += 1

            # -------------------------------
            # RELATIONSHIP HANDLING (FIXED)
            # -------------------------------
            if asset_data.parent:
                parent_asset = db.query(models.Asset).filter(
                    models.Asset.id == asset_data.parent
                ).first()

                if parent_asset:
                    existing_rel = db.query(models.Relationship).filter(
                        models.Relationship.from_asset_id == asset_obj.id,
                        models.Relationship.to_asset_id == parent_asset.id,
                        models.Relationship.type == "subdomain_of"
                    ).first()

                    if not existing_rel:
                        relationship = models.Relationship(
                            from_asset_id=asset_obj.id,
                            to_asset_id=parent_asset.id,
                            type="subdomain_of"
                        )
                        db.add(relationship)

        except Exception as e:
            db.rollback()
            skipped_count += 1
            print(f"Skipped record {asset_data.id} due to error: {e}")

    # ✅ Commit once after loop
    db.commit()

    return {
        "message": "Import complete",
        "new_assets": imported_count,
        "updated_assets": updated_count,
        "skipped_records": skipped_count
    }


# -------------------------------
# AI ENDPOINTS
# -------------------------------

class AnalyzeRequest(BaseModel):
    asset_id: str


class NLQueryRequest(BaseModel):
    query: str


@app.post("/api/analyze/enrich")
def enrich_asset_endpoint(request: AnalyzeRequest, db: Session = Depends(get_db)):
    asset = db.query(models.Asset).filter(models.Asset.id == request.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset_dict = {
        "id": asset.id,
        "type": asset.type,
        "value": asset.value,
        "tags": asset.tags,
        "metadata": asset.metadata_
    }

    enrichment = ai_layer.enrich_asset(asset_dict)
    return {"asset_id": asset.id, "enrichment": enrichment}


@app.post("/api/analyze/risk")
def risk_score_endpoint(request: AnalyzeRequest, db: Session = Depends(get_db)):
    asset = db.query(models.Asset).filter(models.Asset.id == request.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset_dict = {
        "id": asset.id,
        "type": asset.type,
        "value": asset.value,
        "status": asset.status,
        "metadata": asset.metadata_
    }

    risk_assessment = ai_layer.evaluate_risk(asset_dict)
    return {"asset_id": asset.id, "risk_assessment": risk_assessment}


@app.get("/api/analyze/report")
def generate_inventory_report(db: Session = Depends(get_db)):
    assets = db.query(models.Asset).limit(50).all()

    asset_list = [
        {"type": a.type, "value": a.value, "status": a.status}
        for a in assets
    ]

    report = ai_layer.generate_report(asset_list)
    return {"report": report}


@app.post("/api/analyze/query")
def natural_language_query(request: NLQueryRequest):
    if not request.query or not request.query.strip():
        return {"error": "Query cannot be empty"}

    try:
        result = ai_layer.nl_asset_query(request.query)

        return {
            "query": request.query,
            "result": result
        }

    except Exception as e:
        return {
            "query": request.query,
            "error": str(e),
            "type": "error"
        }
