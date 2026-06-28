from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from app.enums import AssetType, AssetStatus, RelationshipType


class AssetRelationshipImport(BaseModel):
    target_asset_id: str
    type: RelationshipType


class AssetImport(BaseModel):
    id: str
    type: AssetType
    value: str
    status: AssetStatus = AssetStatus.ACTIVE
    source: Optional[str] = "import"
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="metadata")

    parent: Optional[str] = None
    covers: Optional[str] = None
    ip_address: Optional[str] = None
    technologies: List[str] = Field(default_factory=list)


class RelatedAsset(BaseModel):
    id: str
    type: str
    value: str


class RelationshipResponse(BaseModel):
    direction: str
    type: RelationshipType
    target_asset: RelatedAsset


class AssetRelationshipsResponse(BaseModel):
    asset_id: str
    relationships: List[RelationshipResponse]


class AnalyzeRequest(BaseModel):
    asset_id: str


class NLQueryRequest(BaseModel):
    query: str
