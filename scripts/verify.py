"""Verify runtime image/health and recent workload logs against Pulumi outputs."""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def query(command: list[str]) -> dict:
    return json.loads(subprocess.check_output(command, cwd=ROOT, text=True))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def fib_pair(n: int) -> tuple[int, int]:
    """Independently verify observed results using fast doubling."""
    if n == 0:
        return 0, 1
    a, b = fib_pair(n // 2)
    c, d = a * (2 * b - a), a * a + b * b
    return (d, c + d) if n % 2 else (c, d)


def wait_for_service(aws: list[str], outputs: dict, timeout: float) -> dict:
    """Wait boundedly for ECS rollout completion beyond provider steady state."""
    deadline = time.monotonic() + timeout
    while True:
        services = query(
            aws
            + [
                "ecs",
                "describe-services",
                "--cluster",
                outputs["clusterName"],
                "--services",
                outputs["serviceName"],
            ]
        )["services"]
        require(len(services) == 1, "Expected exactly one ECS service")
        service = services[0]
        deployments = service["deployments"]
        require(
            not any(d.get("rolloutState") == "FAILED" for d in deployments),
            "ECS rollout failed",
        )
        if (
            service["desiredCount"] == service["runningCount"] == 1
            and service["pendingCount"] == 0
            and deployments
            and all(d.get("rolloutState") == "COMPLETED" for d in deployments)
        ):
            return service
        require(
            time.monotonic() < deadline, "Timed out awaiting healthy completed rollout"
        )
        time.sleep(min(5, max(0, deadline - time.monotonic())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", help="optional local profile; omit for ECS role credentials"
    )
    parser.add_argument("--wait-seconds", type=float, default=180)
    args = parser.parse_args()
    outputs = query(["pulumi", "stack", "output", "--stack", "devops-demo", "--json"])
    aws = ["aws", "--region", outputs["region"]]
    if args.profile:
        aws.extend(["--profile", args.profile])
    wait_for_service(aws, outputs, args.wait_seconds)
    arns = query(
        aws
        + [
            "ecs",
            "list-tasks",
            "--cluster",
            outputs["clusterName"],
            "--service-name",
            outputs["serviceName"],
            "--desired-status",
            "RUNNING",
        ]
    )["taskArns"]
    require(len(arns) == 1, "Expected one running task")
    task = query(
        aws
        + [
            "ecs",
            "describe-tasks",
            "--cluster",
            outputs["clusterName"],
            "--tasks",
            *arns,
        ]
    )["tasks"][0]
    digest = outputs["imageUri"].split("@", 1)[1]
    require(task["healthStatus"] == "HEALTHY", "ECS worker health is not healthy")
    require(
        task["containers"][0]["imageDigest"] == digest, "Running image digest mismatch"
    )
    require(
        task["taskDefinitionArn"] == outputs["taskDefinitionArn"],
        "Task revision mismatch",
    )
    group = query(
        aws
        + ["ec2", "describe-security-groups", "--group-ids", outputs["securityGroupId"]]
    )["SecurityGroups"][0]
    require(not group["IpPermissions"], "Demo unexpectedly permits inbound traffic")
    stream = "worker/devops-demo/" + arns[0].rsplit("/", 1)[1]
    log_events = query(
        aws
        + [
            "logs",
            "get-log-events",
            "--log-group-name",
            outputs["logGroupName"],
            "--log-stream-name",
            stream,
            "--start-time",
            str(int((time.time() - 120) * 1000)),
            "--limit",
            "100",
            "--start-from-head",
        ]
    )["events"]
    events = [json.loads(e["message"]) for e in log_events]
    completed = [e for e in events if e["event"] == "calculation_completed"]
    require(len(completed) >= 3, "Need three recent completed calculations")
    require(not any(e["level"] == "ERROR" for e in events), "Recent workload error")
    for event in completed:
        require(0 <= event["n"] <= 99, "N outside configured range")
        require(
            int(event["result"]) == fib_pair(event["n"])[0], "Wrong Fibonacci result"
        )
        require(event["duration_ns"] > 0, "Missing positive duration")
        require(event["cpu_duration_ns"] >= 0, "Missing CPU measurement")
        require(event["peak_rss_bytes"] > 0, "Missing memory measurement")
        require(event["release_id"] != "local", "Missing release identity")
    timestamps = [datetime.fromisoformat(e["timestamp"]) for e in completed]
    gaps = [(b - a).total_seconds() for a, b in pairwise(timestamps)]
    require(all(4.9 <= gap <= 6 for gap in gaps), "Unexpected five-second cadence")
    require(
        (datetime.now(UTC) - timestamps[-1]).total_seconds() < 20, "Workload logs stale"
    )
    report = {
        "verified_at": datetime.now(UTC).isoformat(),
        "region": outputs["region"],
        "cluster": outputs["clusterName"],
        "service": outputs["serviceName"],
        "running_tasks": 1,
        "health": task["healthStatus"],
        "task_arn": arns[0],
        "task_definition": task["taskDefinitionArn"],
        "image_uri": outputs["imageUri"],
        "release_id": completed[-1]["release_id"],
        "no_inbound_rules": True,
        "completed_calculations_in_recent_window": len(completed),
        "calculation_gap_seconds_min_max": [min(gaps), max(gaps)],
        "wall_duration_ns_min_max": [
            min(e["duration_ns"] for e in completed),
            max(e["duration_ns"] for e in completed),
        ],
        "cloudwatch_log_group": outputs["logGroupName"],
        "cloudwatch_log_stream": stream,
        "sample_calculation": completed[-1],
        "scope": "Snapshot verification, not an availability/recovery guarantee",
    }
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts" / "deployment-verification.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
