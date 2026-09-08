"""Phase 1.7 — the recipes stack, and the object store it depends on.

Health endpoints do not cover what actually broke here. Every failure this
service hit in practice was invisible to a `/health` probe:

  - MinIO ran for days with no bucket. The API answered 200, the upload failed
    with a config-shaped error, and nothing in either service logged a cause.
  - jarvis.ocr.jobs had no consumer. Uploads succeeded, jobs queued, and the app
    spun until it timed out — with a clean log on both sides.
  - `rq` was missing from the OCR image, so completions were LPUSHed onto a plain
    list nobody reads. The job never failed; it just never finished.

So these assert the wiring between the parts rather than the liveness of each
one. Skipped wholesale when the lane did not deploy recipes.
"""
from __future__ import annotations

import json

import pytest
import requests

from conftest import docker_exec, docker_inspect

RECIPES = "jarvis-recipes-server"
OCR = "jarvis-ocr-service"
MINIO = "jarvis-minio"

pytestmark = pytest.mark.skipif(
    docker_inspect(RECIPES, "{{.State.Status}}") is None,
    reason="recipes not deployed in this lane",
)


# ── the object store ─────────────────────────────────────────────────────────


def test_bucket_init_completed() -> None:
    """The one-shot ran and succeeded.

    A non-zero exit here means the buckets do not exist, which surfaces much
    later as a failed upload that reads like an application bug.
    """
    status = docker_inspect("jarvis-minio-init", "{{.State.Status}}")
    assert status == "exited", f"minio-init is '{status}', expected it to have run and exited"

    code = docker_inspect("jarvis-minio-init", "{{.State.ExitCode}}")
    assert code == "0", f"minio-init exited {code}; the buckets were not created"


def test_the_bucket_recipes_uploads_to_exists() -> None:
    """MinIO does not create a bucket on first write.

    Without this the store is healthy, empty, and every photo import fails.
    """
    bucket = _recipes_env("S3_BUCKET")
    assert bucket, "recipes has no S3_BUCKET configured"

    result = docker_exec(
        MINIO,
        [
            "sh",
            "-c",
            # `mc` is not in the minio server image, but the data directory is:
            # a bucket is a directory under /data. Cheaper than another
            # container, and it asserts the same fact.
            f"test -d /data/{bucket} && echo present || echo missing",
        ],
    )
    assert result is not None, "could not exec into minio"
    assert "present" in result.stdout, f"bucket '{bucket}' does not exist in MinIO"


def test_recipes_can_reach_the_object_store() -> None:
    """Configured endpoint, resolved over the compose network.

    Points at localhost in a container and every upload fails with a connection
    error — which is what the endpoint was set to before this was wired up.
    """
    endpoint = _recipes_env("S3_ENDPOINT_URL")
    assert endpoint, "recipes has no S3_ENDPOINT_URL"
    assert "localhost" not in endpoint and "127.0.0.1" not in endpoint, (
        f"S3_ENDPOINT_URL is {endpoint}: localhost inside a container is the container"
    )

    result = docker_exec(
        RECIPES,
        ["python", "-c", f"import urllib.request;urllib.request.urlopen('{endpoint}/minio/health/live',timeout=10)"],
    )
    assert result is not None and result.returncode == 0, (
        f"recipes cannot reach the object store at {endpoint}: {result.stderr if result else 'no result'}"
    )


def test_path_style_addressing_is_on() -> None:
    """MinIO does not serve virtual-host style, which is boto3's default."""
    assert _recipes_env("S3_FORCE_PATH_STYLE", "").lower() == "true"


# ── the queue handoff ────────────────────────────────────────────────────────


def test_every_ocr_queue_has_a_consumer() -> None:
    """The failure with no symptom.

    Recipes fans an image out to each queue in OCR_QUEUES and waits. A queue
    nobody consumes does not error: the job sits there and the app spins until
    it times out. Only the deployment can see that the two sides agree.
    """
    fanout = [q.strip() for q in _recipes_env("OCR_QUEUES", "").split(",") if q.strip()]
    assert fanout, "recipes has no OCR_QUEUES configured"

    consumed = _env_of("jarvis-ocr-worker", "OCR_QUEUE_NAME")
    assert consumed, "the OCR worker declares no queue"

    assert consumed in fanout, (
        f"the OCR worker consumes '{consumed}' but recipes publishes to {fanout} — "
        "images would queue forever"
    )


def test_the_ocr_worker_can_reply_over_rq() -> None:
    """Completions go back through RQ, not a raw list push.

    `rq` was in pyproject.toml but not requirements.txt, so the image had no
    RQ and queue_client silently LPUSHed onto a plain list of the same name that
    nothing reads. Nothing failed; nothing finished.
    """
    result = docker_exec("jarvis-ocr-worker", ["python", "-c", "import rq"])
    assert result is not None and result.returncode == 0, (
        "the OCR worker image has no `rq`: completions would go to a list nobody consumes"
    )


def test_both_sides_share_a_redis() -> None:
    recipes_redis = _recipes_env("REDIS_HOST", "redis")
    ocr_redis = _env_of("jarvis-ocr-worker", "REDIS_HOST") or "redis"
    assert recipes_redis == ocr_redis, (
        f"recipes talks to redis '{recipes_redis}', the OCR worker to '{ocr_redis}'"
    )


# ── the API itself ───────────────────────────────────────────────────────────


def test_recipes_requires_a_token() -> None:
    """The recipe box is household data; an unauthenticated read is a leak."""
    response = requests.get("http://localhost:7030/recipes", timeout=15)
    assert response.status_code in (401, 403), (
        f"GET /recipes without a token returned {response.status_code}"
    )


def test_the_planner_and_grocery_routes_are_mounted() -> None:
    """A router that failed to register 404s, which reads as a client bug."""
    spec = requests.get("http://localhost:7030/openapi.json", timeout=15).json()
    paths = set(spec.get("paths", {}))

    for route in ("/planner/plans", "/shopping-list", "/grocery/cart", "/meal-plans/random"):
        assert route in paths, f"{route} is not mounted"


# ── helpers ──────────────────────────────────────────────────────────────────


def _env_of(container: str, key: str) -> str | None:
    """One environment variable as the running container actually sees it."""
    raw = docker_inspect(container, "{{json .Config.Env}}")
    if not raw:
        return None
    for entry in json.loads(raw):
        name, _, value = entry.partition("=")
        if name == key:
            return value
    return None


def _recipes_env(key: str, default: str | None = None) -> str:
    return _env_of(RECIPES, key) or (default if default is not None else "")
