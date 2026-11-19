AWS_PROFILE ?= roland
export AWS_PROFILE

.PHONY: install check test preview up deploy verify logs status destroy

install:
	uv sync --locked

check:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest

preview:
	pulumi preview

up:
	pulumi up --yes

deploy:
	uv run python scripts/deploy.py --profile $(AWS_PROFILE)

verify:
	uv run python scripts/verify.py --profile $(AWS_PROFILE)

logs:
	aws --profile $(AWS_PROFILE) --region $$(pulumi stack output region) logs tail $$(pulumi stack output logGroupName) --follow

status:
	aws --profile $(AWS_PROFILE) --region $$(pulumi stack output region) ecs describe-services --cluster $$(pulumi stack output clusterName) --services $$(pulumi stack output serviceName) --query 'services[].{status:status,running:runningCount,desired:desiredCount,deployments:deployments[].rolloutState}'

destroy:
	pulumi destroy
