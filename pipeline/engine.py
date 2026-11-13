import logging
from datetime import datetime, timezone

from .db import SessionLocal
from .models import PipelineRun, StageRun, Status
from .stages import STAGES

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(service: str, namespace: str, image: str) -> PipelineRun:
    with SessionLocal() as db:
        run = PipelineRun(service=service, namespace=namespace, image=image)
        run.stages = [StageRun(position=i, name=name) for i, (name, _) in enumerate(STAGES)]
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def execute(run_id: int) -> None:
    """Run each stage in order, persisting state after every transition."""
    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        run.status = Status.RUNNING
        db.commit()

        funcs = dict(STAGES)
        for stage in run.stages:
            stage.status, stage.started_at = Status.RUNNING, _now()
            db.commit()
            try:
                stage.message = funcs[stage.name](run)
                stage.status = Status.SUCCEEDED
            except Exception as exc:  # noqa: BLE001 - any failure fails the stage
                log.exception("stage %s failed for run %s", stage.name, run_id)
                stage.status, stage.message = Status.FAILED, str(exc)[:2000]
            stage.finished_at = _now()
            db.commit()
            if stage.status is Status.FAILED:
                run.status = Status.FAILED
                break
        else:
            run.status = Status.SUCCEEDED

        run.finished_at = _now()
        db.commit()
