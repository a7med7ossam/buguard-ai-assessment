from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enums import AssetType, AssetStatus

class AssetImport(BaseModel):
    id: str
    type: AssetType
    value: str
    status: AssetStatus = AssetStatus.ACTIVE
    source: Optional[str] = "import"
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="metadata")
    parent: Optional[str] = None


class RelationshipResponse(BaseModel):
    type: str
    target_asset_id: str


class AssetRelationshipsResponse(BaseModel):
    asset_id: str
    relationships: List[RelationshipResponse]


class RelatedAsset(BaseModel):
    id: str
    type: str
    value: str


class AssetContextResponse(BaseModel):
    asset: RelatedAsset
    parents: List[RelatedAsset]
    children: List[RelatedAsset]


class AnalyzeRequest(BaseModel):
    asset_id: str


class NLQueryRequest(BaseModel):
    query: str
