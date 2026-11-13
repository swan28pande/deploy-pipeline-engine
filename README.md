# Deployment Pipeline Engine

A minimal Python service that runs multi-stage deployment pipelines for Kubernetes services and tracks each run's state in MySQL.

Each pipeline run goes through these stages in order:

1. **verify_image** – checks that the image tag exists in AWS ECR (skipped if the image isn't from ECR).
2. **deploy** – patches the Kubernetes Deployment to use the new image.
3. **wait_rollout** – waits until every replica is updated and available.

Every run and stage is saved to MySQL as `PENDING`, `RUNNING`, `SUCCEEDED` or `FAILED`. If a stage fails, the pipeline stops there.

## Run

```bash
docker compose up -d                 # MySQL
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn pipeline.main:app --reload
```

The service uses your local kubeconfig, or the in-cluster config when it runs inside Kubernetes. It uses the standard AWS credential chain for ECR.

## API

```bash
# Start a pipeline
curl -s -X POST localhost:8000/pipelines -H 'Content-Type: application/json' \
  -d '{"service": "web", "namespace": "default", "image": "nginx:1.27"}'

# Check status
curl -s localhost:8000/pipelines/1
curl -s localhost:8000/pipelines
```

## Config

| Env var                   | Default                                                     |
|---------------------------|-------------------------------------------------------------|
| `DATABASE_URL`            | `mysql+pymysql://pipeline:pipeline@localhost:3306/pipelines` |
| `AWS_REGION`              | `us-east-1`                                                 |
| `ROLLOUT_TIMEOUT_SECONDS` | `300`                                                       |

To add a stage, write a function in `pipeline/stages.py` and add it to `STAGES`.
