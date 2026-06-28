from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.enums import RelationshipType


def create_relationship(
    db: Session,
    from_asset_id: str,
    to_asset_id: str,
    relationship_type: RelationshipType,
):
    """
    Create a relationship if (and only if):

    1. The target asset exists.
    2. The identical relationship doesn't already exist (idempotent).
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


def get_asset_relationships(db: Session, asset_id: str) -> dict:
    """
    Return an asset together with the graph of assets directly around it
    (both outgoing and incoming edges).
    """
    asset = (
        db.query(models.Asset)
        .filter(models.Asset.id == asset_id)
        .first()
    )

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

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

    # Outgoing edges: this asset -> target
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

    # Incoming edges: source -> this asset
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
