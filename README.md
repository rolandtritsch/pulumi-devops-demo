# Pulumi DevOps Demo

The `devops-demo` stack runs [python-devops-demo][app] as a single AWS ECS Fargate
worker and publishes its container to private ECR. It uses the existing default
VPC/public subnets in `eu-west-1`, following the neighboring Pulumi projects.

See the [initial deployment verification][verification] for the running image,
observed results, completed checks, and remaining security findings.

## Resources

- ECR repository `python-devops-demo`, immutable tags, AES256 encryption, and
  scan-on-push enabled. Automatic image expiry is intentionally omitted so it
  cannot remove a deployed or known-good rollback image.
- ECS cluster/service `devops-demo`, one 0.25-vCPU / 512-MiB Linux x86_64 task.
- CloudWatch log group `/ecs/devops-demo`, seven-day retention.
- A security group with **no inbound rules**, and HTTPS outbound access.
- An ECS execution role scoped to image pulls and log writes. The application
  has no AWS task role, secrets, persistent storage, or database.

Tasks receive public IPv4 addresses for outbound ECR/CloudWatch connectivity;
the security group blocks inbound traffic, and health endpoints bind only to
container loopback. This avoids NAT gateways, VPC endpoint charges, and a load
balancer for a small background-worker demo. This is not a public HTTP SaaS API
or a production availability architecture. One task can be replaced on failure;
it is not a highly available or durable job-processing system.

The task uses a non-root user and read-only root filesystem. ECS probes
`/healthz`, replaces unhealthy tasks, and uses a deployment circuit breaker.
Rollouts can temporarily run two tasks, so two independent Fibonacci loops can
produce logs while a replacement is becoming healthy. No scheduled calculation
is guaranteed to survive task replacement. Lost computations are disposable.

## Setup and deployment

Requires AWS credentials/profile, Pulumi login, uv, and Docker. Keep the
application repository next to this repository, or use `--source` explicitly.

```bash
uv sync --locked
pulumi stack select devops-demo  # use `pulumi stack init devops-demo` once
pulumi config set aws:profile roland
pulumi config set aws:region eu-west-1
make check test
make preview
make deploy
make verify
```

`make deploy` first applies the stack. Without `imageDigest`, this bootstraps
ECR, the cluster, logging, and access/network resources only. It then builds a
digest-pinned Python base image, uses a hash of the Dockerfile/Python sources as
the immutable image tag and release identity, pushes to ECR, records the returned
registry digest in stack configuration, and applies the ECS deployment. The
service waits for steady state. New builds pass a three-cycle, read-only,
network-isolated container smoke test before publication. Repeating deployment
reuses a matching source
image rather than overwriting an immutable tag. `make verify` checks ECS health,
the running digest, absence of inbound access, and recent CloudWatch calculation
results, performance fields, and cadence. It waits up to 180 seconds for the ECS
rollout-completed flag, which can lag provider steady state, and fails on a
failed rollout or missing evidence. It saves a JSON report in `artifacts/`.

Source hashes identify the actual build inputs, including uncommitted changes;
they are not signed provenance or a substitute for a source-control release.
No Git commit or push is performed by this script. The base image is pinned in
the application Dockerfile and must be deliberately refreshed for patches.

## Observe, suspend, roll back

```bash
make status
make logs
# Suspend compute; retained images/logs can still incur storage charges.
pulumi config set desiredCount 0
make up
# Resume.
pulumi config set desiredCount 1
make up
# Deploy a known-good immutable image from this repository.
pulumi config set imageDigest sha256:<64-hex-digest>
make preview up
```

The app's JSON completion events contain result, calculation wall/CPU time,
memory high-water mark, and uptime. ECS provides container health; application
metrics are container-local and have no scraper/dashboard in this initial stack.
ECR scan-on-push is not a penetration test or a release vulnerability gate.

## Teardown and operating boundaries

`make destroy` previews and confirms teardown through Pulumi. ECR deliberately
refuses deletion while it contains images; explicitly decide which images can
be removed before emptying it. The shared VPC/subnets are data sources and are
never destroyed by this stack. Running Fargate, public IPv4, logs, and images
incur AWS charges; no autoscaling or other ongoing infrastructure is provisioned.

The [Company design][company] will use this as its first target. No agents,
security testing, fault injection, or autonomous cloud mutations are enabled by
these repositories. Service objectives remain a separate operating-contract
decision; health freshness is an implemented probe threshold, not an SLO.

[app]: https://github.com/rolandtritsch/python-devops-demo
[company]: https://github.com/rolandtritsch/pcc-devops-demo
[verification]: docs/deployment.md
