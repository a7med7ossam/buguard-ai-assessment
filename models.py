from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, UniqueConstraint
from database import Base
import datetime
import uuid


class Asset(Base):
    __tablename__ = "assets"

    __table_args__ = (
        UniqueConstraint("type", "value", name="uq_asset_type_value"),
    )

    id = Column(String, primary_key=True, index=True)
    type = Column(String, nullable=False) # domain, subdomain, ip_address, etc.
    value = Column(String, nullable=False) 
    status = Column(String, default="active") # active, stale, archived
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
    