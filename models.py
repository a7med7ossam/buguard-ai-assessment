from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, UniqueConstraint, Enum
from database import Base
from enums import AssetType, AssetStatus
import datetime
import uuid


class Asset(Base):
    __tablename__ = "assets"

    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_asset_type_value"),
    )


    id = Column(String, primary_key=True, index=True)

    type = Column(
        Enum(
            AssetType,
            name="asset_type_enum",
            native_enum=False
        ),
        nullable=False
    )

    value = Column(String, nullable=False) 

    status = Column(
        Enum(
            AssetStatus,
            name="asset_status_enum",
            native_enum=False
        ),
        default=AssetStatus.ACTIVE,
        nullable=False
    )

    first_seen = Column(DateTime, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String)
    tags = Column(JSON, default=list) # Storing arrays as JSON is flexible
    metadata_ = Column("metadata", JSON, default=dict) # Named metadata_ to avoid SQLAlchemy conflicts



class Relationship(Base):
    __tablename__ = "relationships"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    from_asset_id = Column(String, ForeignKey("assets.id"), nullable=False)
    to_asset_id = Column(String, ForeignKey("assets.id"), nullable=False)
    
    type = Column(String, nullable=False)  
    