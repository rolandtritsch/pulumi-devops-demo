"""Pure validation and task rendering, separate from cloud resource creation."""

import json
import re


def validate_digest(value: str | None) -> str | None:
    """Allow bootstrap without an image, otherwise require immutable identity."""
    if value is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError(
            "imageDigest must be sha256 followed by 64 lowercase hex digits"
        )
    return value


def validate_count(value: int) -> int:
    """Keep this demo to one worker, with zero available for suspension."""
    if isinstance(value, bool) or value not in (0, 1):
        raise ValueError("desiredCount must be 0 or 1 for this limited demo")
    return value


def container_definition(image: str, log_group: str, region: str) -> str:
    """Render an observable, non-root, read-only worker task."""
    return json.dumps(
        [
            {
                "name": "devops-demo",
                "image": image,
                "essential": True,
                "user": "10001:10001",
                "readonlyRootFilesystem": True,
                "stopTimeout": 15,
                "healthCheck": {
                    "command": [
                        "CMD",
                        "python",
                        "-c",
                        "import urllib.request; "
                        "urllib.request.urlopen('http://127.0.0.1:8080/healthz', "
                        "timeout=2).read()",
                    ],
                    "interval": 15,
                    "timeout": 3,
                    "retries": 3,
                    "startPeriod": 10,
                },
                "logConfiguration": {
                    "logDriver": "awslogs",
                    "options": {
                        "awslogs-group": log_group,
                        "awslogs-region": region,
                        "awslogs-stream-prefix": "worker",
                        "mode": "non-blocking",
                        "max-buffer-size": "1m",
                    },
                },
            }
        ]
    )
