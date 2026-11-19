"""Bootstrap infrastructure, publish an image, and deploy its immutable digest."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, capture=False, input_text=None, env=None) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        input=input_text,
        text=True,
        check=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def source_identity(source: Path) -> str:
    """Hash the actual build inputs, including uncommitted source changes."""
    files = [
        source / "Dockerfile",
        source / ".dockerignore",
        *sorted((source / "src").rglob("*.py")),
    ]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(source).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="roland")
    parser.add_argument(
        "--source", type=Path, default=ROOT.parent / "python-devops-demo"
    )
    args = parser.parse_args()
    source = args.source.resolve()
    revision = source_identity(source)
    tag = "src-" + revision[:20]
    env = {**os.environ, "AWS_PROFILE": args.profile}

    # On a fresh stack this creates ECR/cluster, without starting an absent image.
    run(["pulumi", "up", "--stack", "devops-demo", "--yes"], env=env)
    outputs = json.loads(
        run(
            ["pulumi", "stack", "output", "--stack", "devops-demo", "--json"],
            capture=True,
            env=env,
        )
    )
    repo, region = outputs["ecrRepositoryUrl"], outputs["region"]
    aws = ["aws", "--profile", args.profile, "--region", region]
    account = run(
        aws + ["sts", "get-caller-identity", "--query", "Account", "--output", "text"],
        capture=True,
    )
    if repo.split(".")[0] != account:
        raise RuntimeError("AWS CLI profile and Pulumi ECR target accounts differ")
    existing = json.loads(
        run(
            aws
            + [
                "ecr",
                "list-images",
                "--repository-name",
                outputs["ecrRepositoryName"],
                "--filter",
                "tagStatus=TAGGED",
                "--output",
                "json",
            ],
            capture=True,
        )
    )
    image = next((i for i in existing["imageIds"] if i.get("imageTag") == tag), None)
    if image:
        image_digest = image["imageDigest"]
        print(f"Reusing immutable source image {repo}:{tag}", flush=True)
    else:
        run(
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "--provenance=false",
                "--build-arg",
                f"SOURCE_REVISION={revision}",
                "--tag",
                f"{repo}:{tag}",
                str(source),
            ]
        )
        smoke = run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--network=none",
                f"{repo}:{tag}",
                "--interval",
                "0.05",
                "--iterations",
                "3",
            ],
            capture=True,
        )
        events = [json.loads(line) for line in smoke.splitlines()]
        completed = [e for e in events if e["event"] == "calculation_completed"]
        if len(completed) != 3 or any(e["release_id"] != revision for e in completed):
            raise RuntimeError(
                "Container smoke test failed; image will not be published"
            )
        print("Passed three-cycle read-only container smoke test", flush=True)
        password = run(aws + ["ecr", "get-login-password"], capture=True)
        run(
            [
                "docker",
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                repo.split("/")[0],
            ],
            input_text=password,
        )
        run(["docker", "push", f"{repo}:{tag}"])
        image_digest = run(
            aws
            + [
                "ecr",
                "describe-images",
                "--repository-name",
                outputs["ecrRepositoryName"],
                "--image-ids",
                f"imageTag={tag}",
                "--query",
                "imageDetails[0].imageDigest",
                "--output",
                "text",
            ],
            capture=True,
        )
    run(
        [
            "pulumi",
            "config",
            "set",
            "--stack",
            "devops-demo",
            "imageDigest",
            image_digest,
        ],
        env=env,
    )
    run(["pulumi", "up", "--stack", "devops-demo", "--yes"], env=env)
    print(json.dumps({"image": f"{repo}@{image_digest}", "source_sha256": revision}))


if __name__ == "__main__":
    main()
