from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import datetime

import models
import schemas
from database import engine, get_db
from enums import AssetType, AssetStatus, RelationshipType

import ai_layer
from pydantic import BaseModel

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Buguard Asset Management API")


def create_relationship(
    db: Session,
    from_asset_id: str,
    to_asset_id: str,
    relationship_type: RelationshipType,
):
    """
    Create a relationship if:
    1. Target asset exists.
    2. Same relationship doesn't already exist.
    """

    target = (
        db.query(models.Asset)
        .filter(models.Asset.id == to_asset_id)
        .first()
    )

    if not target:
        return

    existing = (
        db.query(models.Relationship)
        .filter(
            models.Relationship.from_asset_id == from_asset_id,
            models.Relationship.to_asset_id == to_asset_id,
            models.Relationship.type == relationship_type,
        )
        .first()
    )

    if existing:
        return

    db.add(
        models.Relationship(
            from_asset_id=from_asset_id,
            to_asset_id=to_asset_id,
            type=relationship_type,
        )
    )


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

            
            if existing_asset:
                existing_asset.last_seen = datetime.datetime.utcnow()
                existing_asset.status = AssetStatus.ACTIVE

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

            
            if asset_data.parent:
                create_relationship(
                    db=db,
                    from_asset_id=asset_obj.id,
                    to_asset_id=asset_data.parent,
                    relationship_type=RelationshipType.SUBDOMAIN_OF,
                )

            if asset_data.covers:
                create_relationship(
                    db=db,
                    from_asset_id=asset_obj.id,
                    to_asset_id=asset_data.covers,
                    relationship_type=RelationshipType.CERTIFICATE_FOR,
                )

            if asset_data.ip_address:
                create_relationship(
                    db=db,
                    from_asset_id=asset_obj.id,
                    to_asset_id=asset_data.ip_address,
                    relationship_type=RelationshipType.SERVICE_ON,
                )

            for technology in asset_data.technologies:
                create_relationship(
                    db=db,
                    from_asset_id=technology,
                    to_asset_id=asset_obj.id,
                    relationship_type=RelationshipType.TECHNOLOGY_USED_BY,
                )

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


@app.get(
    "/api/assets/{asset_id}/relationships",
    response_model=schemas.AssetRelationshipsResponse
)
def get_asset_relationships(
    asset_id: str,
    db: Session = Depends(get_db)
):
    asset = db.query(models.Asset).filter(
        models.Asset.id == asset_id
    ).first()

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found"
        )

    outgoing_relationships = (
        db.query(models.Relationship)
        .filter(models.Relationship.from_asset_id == asset_id)
        .all()
    )

    incoming_relationships = (
        db.query(models.Relationship)
        .filter(models.Relationship.to_asset_id == asset_id)
        .all()
    )

    relationship_list = []

    # Outgoing
    for rel in outgoing_relationships:
        target = (
            db.query(models.Asset)
            .filter(models.Asset.id == rel.to_asset_id)
            .first()
        )

        if target:
            relationship_list.append(
                {
                    "direction": "outgoing",
                    "type": rel.type,
                    "target_asset": {
                        "id": target.id,
                        "type": target.type,
                        "value": target.value,
                    },
                }
            )

    # Incoming
    for rel in incoming_relationships:
        source = (
            db.query(models.Asset)
            .filter(models.Asset.id == rel.from_asset_id)
            .first()
        )

        if source:
            relationship_list.append(
                {
                    "direction": "incoming",
                    "type": rel.type,
                    "target_asset": {
                        "id": source.id,
                        "type": source.type,
                        "value": source.value,
                    },
                }
            )

    return {
        "asset_id": asset_id,
        "relationships": relationship_list,
    }


@app.get(
    "/api/assets/{asset_id}/context",
    response_model=schemas.AssetContextResponse
)
def get_asset_context(
    asset_id: str,
    db: Session = Depends(get_db)
):
    asset = db.query(models.Asset).filter(
        models.Asset.id == asset_id
    ).first()

    if not asset:
        raise HTTPException(
            status_code=404,
            detail="Asset not found"
        )

    # Parents
    parent_relationships = db.query(models.Relationship).filter(
        models.Relationship.from_asset_id == asset_id
    ).all()

    parents = []

    for rel in parent_relationships:
        parent = db.query(models.Asset).filter(
            models.Asset.id == rel.to_asset_id
        ).first()

        if parent:
            parents.append({
                "id": parent.id,
                "type": parent.type,
                "value": parent.value
            })

    # Children
    child_relationships = db.query(models.Relationship).filter(
        models.Relationship.to_asset_id == asset_id
    ).all()

    children = []

    for rel in child_relationships:
        child = db.query(models.Asset).filter(
            models.Asset.id == rel.from_asset_id
        ).first()

        if child:
            children.append({
                "id": child.id,
                "type": child.type,
                "value": child.value
            })

    return {
        "asset": {
            "id": asset.id,
            "type": asset.type,
            "value": asset.value
        },
        "parents": parents,
        "children": children
    }


@app.post("/api/analyze/enrich")
def enrich_asset_endpoint(request: schemas.AnalyzeRequest, db: Session = Depends(get_db)):
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
def risk_score_endpoint(request: schemas.AnalyzeRequest, db: Session = Depends(get_db)):
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
    assets = db.query(models.Asset).all()

    asset_list = [
        {"type": a.type, "value": a.value, "status": a.status}
        for a in assets
    ]

    report = ai_layer.generate_report(asset_list)
    return {"report": report}


@app.post("/api/analyze/query")
def natural_language_query(request: schemas.NLQueryRequest):
    if not request.query or not request.query.strip():
        return {"error": "Query cannot be empty"}

    try:
        result = ai_layer.nl_asset_query(request.query)

        return {
            "query": request.query,
            **result
        }

    except Exception as e:
        return {
            "query": request.query,
            "error": str(e),
            "type": "error"
        }
