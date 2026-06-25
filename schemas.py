from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class domain(Enum):
    pass


class AssetImport(BaseModel):
    id: str
    type: str
    value: str
    status: Optional[str] = "active"
    source: Optional[str] = "import"
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, alias="metadata")
    parent: Optional[str] = None