from fastapi import FastAPI

from app import models
from app.database import engine
from app.routers import imports, relationships, analyze

# Create tables on startup. For a real deployment this would move to Alembic
# migrations; for this self-contained task, create_all keeps setup to one step.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Buguard Asset Management API")

app.include_router(imports.router)
app.include_router(relationships.router)
app.include_router(analyze.router)


@app.get("/health", tags=["meta"])
def health_check():
    """Liveness probe used by docker-compose's healthcheck."""
    return {"status": "ok"}
