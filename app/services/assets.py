import datetime
from typing import List

from sqlalchemy.orm import Session

from app import models, schemas
from app.enums import AssetStatus, RelationshipType
from app.services.merge import merge_metadata
from app.services.relationships import create_relationship


def merge_ai_enrichment(asset, enrichment: dict):
    """
    Merge AI-generated enrichment fields into an asset's metadata. Existing
    metadata is preserved; only the enrichment fields are added/updated.
    """
    metadata = asset.metadata_ or {}

    metadata.update(
        {
            "environment": enrichment["environment"],
            "criticality": enrichment["criticality"],
            "category": enrichment["category"],
            "last_ai_enrichment": datetime.datetime.now(datetime.UTC).isoformat(),
        }
    )

    asset.metadata_ = metadata


def import_assets(db: Session, assets: List[schemas.AssetImport]) -> dict:
    """
    Bulk-import assets with deduplication.

    For each record:
      * Dedup is keyed on (type, value). A re-sighted asset updates last_seen,
        flips status back to ACTIVE, and merges tags + metadata.
      * A brand-new (type, value) whose `id` collides with an existing asset is
        rejected for that record only.
      * Relationship edges (parent / covers / ip_address / technologies) are
        created idempotently.

    Each record runs inside a SAVEPOINT, so a single malformed record fails on
    its own without poisoning the rest of the batch.
    """
    imported_count = 0
    updated_count = 0
    skipped_count = 0
    failed_records = []

    for asset_data in assets:
        try:
            with db.begin_nested():
                # 1. Dedup by (type, value)
                existing_asset = (
                    db.query(models.Asset)
                    .filter(
                        models.Asset.type == asset_data.type,
                        models.Asset.value == asset_data.value,
                    )
                    .first()
                )

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
                    # Re-sighting: refresh lifecycle, merge tags + metadata.
                    existing_asset.last_seen = datetime.datetime.now(datetime.UTC)
                    existing_asset.status = AssetStatus.ACTIVE

                    combined_tags = set(existing_asset.tags or [])
                    combined_tags.update(asset_data.tags or [])
                    existing_asset.tags = list(combined_tags)

                    current_metadata = existing_asset.metadata_ or {}
                    new_metadata = asset_data.metadata or {}
                    existing_asset.metadata_ = merge_metadata(
                        current_metadata, new_metadata
                    )

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
                        metadata_=asset_data.metadata,
                    )
                    db.add(new_asset)
                    db.flush()

                    asset_obj = new_asset
                    imported_count += 1

                # 2. Relationship edges
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
                    "reason": str(e),
                }
            )

    # Commit once after the loop.
    db.commit()

    return {
        "message": "Import complete",
        "new_assets": imported_count,
        "updated_assets": updated_count,
        "skipped_records": skipped_count,
        "failed_records": failed_records,
    }
