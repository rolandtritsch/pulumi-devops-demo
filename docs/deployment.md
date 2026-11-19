# Deployment verification — November 19, 2026

Verified at **14:37 UTC** against live AWS state and CloudWatch logs.

| Item | Verified value |
| --- | --- |
| AWS account / profile / region | `519722017377` / `roland` / `eu-west-1` |
| Pulumi stack | `rolandtritsch/devops-demo/devops-demo` |
| ECS cluster / service | `devops-demo` / `devops-demo` |
| Task definition | `devops-demo:2` |
| Running / desired tasks | 1 / 1; no pending tasks |
| Health / rollout | HEALTHY / COMPLETED |
| Task size | 0.25 vCPU / 512 MiB |
| ECR repository | `python-devops-demo` |
| Image tag | `src-6a46bff0dda547da08e9` |
| Inbound security-group rules | None |
| CloudWatch log group | `/ecs/devops-demo` |

Exact running image:

```text
519722017377.dkr.ecr.eu-west-1.amazonaws.com/python-devops-demo@sha256:c8bedab999e6cb5104a4ad68c396cf5b759b97319c87c47c4397ee2de199188f
```

Verification independently recalculated 24 recent logged results using fast
doubling, checked N in 0–99, and confirmed performance/release fields. Observed
completion gaps were 5.000301–5.002486 seconds. Observed calculation wall time was
9,940–106,478 nanoseconds in that window. These are snapshot observations, not
availability, performance capacity, or recovery guarantees.

Example event: N=74, result `1304969544928657`, wall time 106,478 ns, thread CPU
time 19,500 ns, peak RSS 24,772,608 bytes. Logs carry the full source hash
`6a46bff0dda547da08e96c1f3f1de39c49e1c9ffbe178f3779c47b484eadf14c`.

## Validation performed

- 18 application tests and 15 infrastructure/verification tests passed.
- Ruff lint and formatting passed for both repositories.
- Local container health/metrics/default-five-second-loop and graceful shutdown
  passed with a read-only filesystem and dropped capabilities.
- The replacement image passed a three-cycle network-isolated/read-only smoke
  test before publication.
- ECR digest, ECS runtime digest, configured digest, and task definition matched.
- The deployed security group has no inbound rules.
- Pulumi preview with a live refresh reported all nine managed resources
  unchanged (including the stack resource).
- Completed image scanning and [security follow-up][security] are recorded.

Machine-readable evidence is saved to ignored
`artifacts/deployment-verification.json` and `artifacts/image-scan.json`.
Run `make verify` for a current report; this document is a dated snapshot.

## Handoff limits

The worker is running and incurs ongoing AWS charges. There is no public URL,
database, durable queue, metrics scraper, or external alert route. No recovery
fault injection or penetration test was run. Two HIGH glibc findings remain open
after patching zlib. The Operations Company has not been activated, and service
objectives remain undecided.

At verification time the repositories were local and uncommitted. GitHub
publication was subsequently authorized as a separate step; publishing source
does not change the deployed artifact or activate the Operations Company.

[security]: https://github.com/rolandtritsch/python-devops-demo/blob/main/docs/security-findings.md
