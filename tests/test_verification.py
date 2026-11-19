"""Verify bounded rollout waiting and failure handling independently of AWS."""

from unittest.mock import patch

import pytest

from scripts.verify import wait_for_service

OUTPUTS = {"clusterName": "demo", "serviceName": "demo"}


def response(state):
    return {
        "services": [
            {
                "desiredCount": 1,
                "runningCount": 1,
                "pendingCount": 0,
                "deployments": [{"rolloutState": state}],
            }
        ]
    }


def test_running_count_alone_does_not_prove_rollout_completion():
    with patch(
        "scripts.verify.query",
        side_effect=[response("IN_PROGRESS"), response("COMPLETED")],
    ) as query:
        with patch("scripts.verify.time.sleep") as sleep:
            service = wait_for_service(["aws"], OUTPUTS, timeout=10)
    assert service["deployments"][0]["rolloutState"] == "COMPLETED"
    assert query.call_count == 2
    sleep.assert_called_once()


def test_rollout_timeout_is_a_failure():
    with patch("scripts.verify.query", return_value=response("IN_PROGRESS")):
        with pytest.raises(RuntimeError, match="Timed out"):
            wait_for_service(["aws"], OUTPUTS, timeout=0)


def test_failed_rollout_does_not_wait_or_pass():
    with patch("scripts.verify.query", return_value=response("FAILED")):
        with patch("scripts.verify.time.sleep") as sleep:
            with pytest.raises(RuntimeError, match="rollout failed"):
                wait_for_service(["aws"], OUTPUTS, timeout=10)
    sleep.assert_not_called()
