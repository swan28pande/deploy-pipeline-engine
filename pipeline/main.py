from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from . import engine
from .db import Base, SessionLocal, engine as db_engine
from .models import PipelineRun, Status

app = FastAPI(title="Deployment Pipeline Engine")


@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(db_engine)


class RunRequest(BaseModel):
    service: str
    namespace: str = "default"
    image: str


class StageOut(BaseModel):
    name: str
    status: Status
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(BaseModel):
    id: int
    service: str
    namespace: str
    image: str
    status: Status
    created_at: datetime
    finished_at: datetime | None
    stages: list[StageOut]

    model_config = {"from_attributes": True}


@app.post("/pipelines", response_model=RunOut, status_code=202)
def start_pipeline(req: RunRequest, background: BackgroundTasks) -> PipelineRun:
    run = engine.create_run(req.service, req.namespace, req.image)
    background.add_task(engine.execute, run.id)
    return run


@app.get("/pipelines/{run_id}", response_model=RunOut)
def get_pipeline(run_id: int) -> PipelineRun:
    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        if run is None:
            raise HTTPException(404, "pipeline run not found")
        return run


@app.get("/pipelines", response_model=list[RunOut])
def list_pipelines(limit: int = 20) -> list[PipelineRun]:
    with SessionLocal() as db:
        return (
            db.query(PipelineRun).order_by(PipelineRun.id.desc()).limit(limit).all()
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
