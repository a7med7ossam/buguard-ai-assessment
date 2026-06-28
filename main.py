from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List
import datetime

import models
import schemas
from database import engine, get_db
from enums import AssetStatus, RelationshipType

import ai_layer

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Buguard Asset Management API")


def merge_metadata(existing: dict, incoming: dict) -> dict:
    """
    Recursively merge metadata dictionaries.
    Nested dictionaries are merged instead of overwritten.
    """
    merged = existing.copy()

    for key, value in incoming.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = merge_metadata(
                merged[key],
                value
            )
        else:
            merged[key] = value

    return merged


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


def merge_ai_enrichment(asset, enrichment):
    """
    Merge AI-generated enrichment into the asset metadata.
    Existing metadata is preserved while enrichment fields are updated.
    """

    metadata = asset.metadata_ or {}

    metadata.update(
        {
            "environment": enrichment["environment"],
            "criticality": enrichment["criticality"],
            "category": enrichment["category"],
            "last_ai_enrichment": datetime.datetime.now(datetime.UTC).isoformat()
        }
    )

    asset.metadata_ = metadata



@app.post("/api/import")
def import_assets(assets: List[schemas.AssetImport], db: Session = Depends(get_db)):
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    failed_records = []

    for asset_data in assets:
        try:
            with db.begin_nested():

                # 1. Check if asset exists (DEDUP by type + value)
                existing_asset = db.query(models.Asset).filter(
                    models.Asset.type == asset_data.type,
                    models.Asset.value == asset_data.value
                ).first()

                if existing_asset is None:
                    asset_with_same_id = (
                        db.query(models.Asset)
                        .filter(models.Asset.id == asset_data.id)
                        .first()
                    )

                    if asset_with_same_id:
                        raise ValueError(
                            f"Asset ID '{asset_data.id}' is already used by asset "
                            f"'{asset_with_same_id.value}' ({asset_with_same_id.type})."
                        )            


                if existing_asset:
                    existing_asset.last_seen = datetime.datetime.now(datetime.UTC)
                    existing_asset.status = AssetStatus.ACTIVE

                    # Merge tags
                    combined_tags = set(existing_asset.tags or [])
                    combined_tags.update(asset_data.tags or [])
                    existing_asset.tags = list(combined_tags)

                    # Merge metadata
                    current_metadata = existing_asset.metadata_ or {}
                    new_metadata = asset_data.metadata or {}
                    existing_asset.metadata_ = merge_metadata(current_metadata, new_metadata)

                    asset_obj = existing_asset
                    updated_count += 1

                
                else:
                    new_asset = models.Asset(
                        id=asset_data.id,
                        type=asset_data.type,
                        value=asset_data.value,
                        status=asset_data.status,
                        first_seen=datetime.datetime.now(datetime.UTC),
                        last_seen=datetime.datetime.now(datetime.UTC),
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
            skipped_count += 1

            failed_records.append(
                    {
                        "asset_id": asset_data.id,
                        "reason": str(e)
                    }
            )

    # Commit once after loop
    db.commit()

    return {
        "message": "Import complete",
        "new_assets": imported_count,
        "updated_assets": updated_count,
        "skipped_records": skipped_count,
        "failed_records": failed_records
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

    merge_ai_enrichment(asset, enrichment)

    db.commit()
    db.refresh(asset)

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


@app.get(
    "/api/analyze/report",
    response_class=Response,
)
def generate_inventory_report(db: Session = Depends(get_db)):
    assets = db.query(models.Asset).all()

    asset_list = [
        {
            "type": a.type,
            "value": a.value,
            "status": a.status,
        }
        for a in assets
    ]

    report = ai_layer.generate_report(asset_list)

    return Response(
        content=report,
        media_type="text/markdown",
    )


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
