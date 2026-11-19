"""Check deployment identity, safety bounds, and container health configuration."""

import json

import pytest

from pulumi_devops_demo.config import (
    container_definition,
    validate_count,
    validate_digest,
)


def test_bootstrap_and_immutable_digest():
    assert validate_digest(None) is None
    digest = "sha256:" + "a" * 64
    assert validate_digest(digest) == digest


@pytest.mark.parametrize(
    "value", ["latest", "v1", "sha256:abc", "", "sha256:" + "G" * 64]
)
def test_mutable_or_malformed_image_rejected(value):
    with pytest.raises(ValueError):
        validate_digest(value)


@pytest.mark.parametrize("count", [-1, 2, 100, True])
def test_demo_cannot_expand_unbounded(count):
    with pytest.raises(ValueError):
        validate_count(count)


def test_suspension_and_one_worker():
    assert validate_count(0) == 0
    assert validate_count(1) == 1


def test_task_is_observable_and_hardened():
    definition = json.loads(
        container_definition(
            "registry/image@sha256:" + "a" * 64, "/ecs/demo", "eu-west-1"
        )
    )[0]
    assert definition["readonlyRootFilesystem"] is True
    assert definition["user"] == "10001:10001"
    assert definition["stopTimeout"] == 15
    health = definition["healthCheck"]
    assert health["command"][0] == "CMD"
    assert "/healthz" in health["command"][-1]
    assert definition["logConfiguration"]["options"]["awslogs-group"] == "/ecs/demo"
