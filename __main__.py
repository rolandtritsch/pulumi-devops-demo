"""Create the demo's ECR/cluster, then deploy the worker after image publication."""

import json

import pulumi
import pulumi_aws as aws

from pulumi_devops_demo.config import (
    container_definition,
    validate_count,
    validate_digest,
)

cfg = pulumi.Config()
image_digest = validate_digest(cfg.get("imageDigest"))
configured_count = cfg.get_int("desiredCount")
desired_count = validate_count(1 if configured_count is None else configured_count)
region = aws.get_region().region
tags = {"application": "devops-demo", "managed-by": "pulumi"}

repository = aws.ecr.Repository(
    "devops-demo",
    name="python-devops-demo",
    image_tag_mutability="IMMUTABLE",
    image_scanning_configuration={"scan_on_push": True},
    encryption_configurations=[{"encryption_type": "AES256"}],
    force_delete=False,
    tags=tags,
)
cluster = aws.ecs.Cluster("devops-demo", name="devops-demo", tags=tags)
log_group = aws.cloudwatch.LogGroup(
    "devops-demo",
    name="/ecs/devops-demo",
    retention_in_days=7,
    tags=tags,
)

# Reuse the verified default VPC/public subnets; no NAT, ALB, or database.
vpc = aws.ec2.get_vpc(default=True)
subnets = aws.ec2.get_subnets(
    filters=[
        {"name": "vpc-id", "values": [vpc.id]},
        {"name": "map-public-ip-on-launch", "values": ["true"]},
    ]
)
subnet_ids = sorted(subnets.ids)[:2]
if len(subnet_ids) < 2:
    raise ValueError(
        "default VPC must have at least two internet-routed public subnets"
    )

security_group = aws.ec2.SecurityGroup(
    "devops-demo",
    vpc_id=vpc.id,
    description="No inbound access; HTTPS egress for ECR and CloudWatch",
    ingress=[],
    egress=[
        {
            "protocol": "tcp",
            "from_port": 443,
            "to_port": 443,
            "cidr_blocks": ["0.0.0.0/0"],
        }
    ],
    tags=tags,
)
execution_role = aws.iam.Role(
    "devops-demo-execution",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    ),
    tags=tags,
)
execution_policy = aws.iam.RolePolicy(
    "devops-demo-execution",
    role=execution_role.id,
    policy=pulumi.Output.all(repository.arn, log_group.arn).apply(
        lambda arns: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "ecr:GetAuthorizationToken",
                        "Resource": "*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ecr:BatchCheckLayerAvailability",
                            "ecr:GetDownloadUrlForLayer",
                            "ecr:BatchGetImage",
                        ],
                        "Resource": arns[0],
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                        "Resource": arns[1] + ":*",
                    },
                ],
            }
        )
    ),
)

pulumi.export("ecrRepositoryUrl", repository.repository_url)
pulumi.export("ecrRepositoryName", repository.name)
pulumi.export("clusterName", cluster.name)
pulumi.export("logGroupName", log_group.name)
pulumi.export("region", region)
pulumi.export("vpcId", vpc.id)
pulumi.export("subnetIds", subnet_ids)
pulumi.export("securityGroupId", security_group.id)

if image_digest:
    image_uri = repository.repository_url.apply(lambda uri: f"{uri}@{image_digest}")
    task = aws.ecs.TaskDefinition(
        "devops-demo",
        family="devops-demo",
        network_mode="awsvpc",
        requires_compatibilities=["FARGATE"],
        cpu="256",
        memory="512",
        execution_role_arn=execution_role.arn,
        # No application task role: the worker needs no AWS API access.
        runtime_platform={
            "cpu_architecture": "X86_64",
            "operating_system_family": "LINUX",
        },
        container_definitions=pulumi.Output.all(image_uri, log_group.name).apply(
            lambda values: container_definition(values[0], values[1], region)
        ),
        tags=tags,
    )
    service = aws.ecs.Service(
        "devops-demo",
        name="devops-demo",
        cluster=cluster.arn,
        task_definition=task.arn,
        desired_count=desired_count,
        launch_type="FARGATE",
        platform_version="1.4.0",
        deployment_minimum_healthy_percent=100,
        deployment_maximum_percent=200,
        deployment_circuit_breaker={"enable": True, "rollback": True},
        wait_for_steady_state=True,
        network_configuration={
            "subnets": subnet_ids,
            "security_groups": [security_group.id],
            "assign_public_ip": True,
        },
        tags=tags,
        opts=pulumi.ResourceOptions(
            depends_on=[execution_policy],
            custom_timeouts=pulumi.CustomTimeouts(create="15m", update="15m"),
        ),
    )
    pulumi.export("serviceName", service.name)
    pulumi.export("taskDefinitionArn", task.arn)
    pulumi.export("imageUri", image_uri)
else:
    pulumi.export("deploymentStatus", "bootstrap: publish an image and set imageDigest")
