"""Pipeline stages. Each stage takes the run and returns a short status message,
or raises to fail the pipeline."""

import os
import time
from typing import Callable

import boto3
from kubernetes import client, config

from .models import PipelineRun

_k8s_loaded = False


def _apps_api() -> client.AppsV1Api:
    global _k8s_loaded
    if not _k8s_loaded:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        _k8s_loaded = True
    return client.AppsV1Api()


def verify_image(run: PipelineRun) -> str:
    """Confirm the image tag exists in ECR (skipped for non-ECR images)."""
    repo_and_tag = run.image.split("/", 1)[-1]
    if ".dkr.ecr." not in run.image or ":" not in repo_and_tag:
        return "skipped: not an ECR image"
    repo, tag = repo_and_tag.rsplit(":", 1)
    ecr = boto3.client("ecr", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ecr.describe_images(repositoryName=repo, imageIds=[{"imageTag": tag}])
    return f"found {repo}:{tag} in ECR"


def deploy(run: PipelineRun) -> str:
    """Patch the Deployment's first container to the new image."""
    api = _apps_api()
    dep = api.read_namespaced_deployment(run.service, run.namespace)
    container = dep.spec.template.spec.containers[0].name
    patch = {"spec": {"template": {"spec": {"containers": [
        {"name": container, "image": run.image}
    ]}}}}
    api.patch_namespaced_deployment(run.service, run.namespace, patch)
    return f"set {container} image to {run.image}"


def wait_rollout(run: PipelineRun) -> str:
    """Poll until all replicas are updated and available."""
    api = _apps_api()
    timeout = int(os.getenv("ROLLOUT_TIMEOUT_SECONDS", "300"))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        dep = api.read_namespaced_deployment_status(run.service, run.namespace)
        want = dep.spec.replicas or 0
        s = dep.status
        if (
            (s.observed_generation or 0) >= dep.metadata.generation
            and (s.updated_replicas or 0) == want
            and (s.available_replicas or 0) == want
        ):
            return f"{want}/{want} replicas available"
        time.sleep(5)
    raise TimeoutError(f"rollout not complete after {timeout}s")


STAGES: list[tuple[str, Callable[[PipelineRun], str]]] = [
    ("verify_image", verify_image),
    ("deploy", deploy),
    ("wait_rollout", wait_rollout),
]
