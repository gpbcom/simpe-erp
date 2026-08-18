# Shortcuts for the development stack.
#
# The compose files moved under infra/compose/, so every command needs two -f
# flags. Forgetting one is not a typo you notice: `mailpit`, `seed` and the
# whole observability chain are declared *only* in the dev overlay, so a bare
# `docker compose down` leaves them running attached to a network it has just
# deleted — and the next `up` fails with `network <id> not found`, naming the
# network rather than the containers that are really the problem.
#
# Every target here passes both files, which is the whole point of the file.

COMPOSE_FILES := -f infra/compose/docker-compose.yaml \
                 -f infra/compose/docker-compose.dev.yaml
COMPOSE := docker compose $(COMPOSE_FILES)

.DEFAULT_GOAL := help
.PHONY: help up up-build start stop down restart logs ps seed clean urls \
        replan-config

help:  ## List the available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk -F':.*?## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
#  Starting and stopping
# ---------------------------------------------------------------------------

up:  ## Start the whole dev stack in the background
	$(COMPOSE) up -d

up-build:  ## Rebuild the images first, then start
	$(COMPOSE) up -d --build

start:  ## Start containers that were previously stopped
	$(COMPOSE) start

stop:  ## Stop the containers, keeping them and the data
	$(COMPOSE) stop

down:  ## Stop and remove the containers, keeping the data volumes
	$(COMPOSE) down --remove-orphans

restart:  ## Restart every service
	$(COMPOSE) restart

# ---------------------------------------------------------------------------
#  Looking at it
# ---------------------------------------------------------------------------

ps:  ## What is running, and is it healthy
	$(COMPOSE) ps

logs:  ## Follow the logs; pass S=backend for one service
	$(COMPOSE) logs -f $(S)

urls:  ## Print the addresses the stack publishes
	@echo "  Application       http://localhost:5173"
	@echo "  API and docs      http://localhost:8000  ·  /docs  ·  /redoc"
	@echo "  Caught email      http://localhost:8025"
	@echo "  Broker            http://localhost:15672  simple_erp / simple_erp_dev"
	@echo "  Object store      http://localhost:9001  simple_erp_dev / simple_erp_dev_secret"
	@echo "  Grafana           http://localhost:3000  (anonymous admin)"
	@echo "  Prometheus        http://localhost:9090"
	@echo "  Planning worker   http://localhost:9101/health  ·  /ready  ·  /metrics"

# ---------------------------------------------------------------------------
#  Data
# ---------------------------------------------------------------------------

seed:  ## Re-run the seeder. It upserts, so this is always safe
	$(COMPOSE) run --rm seed

clean:  ## Destroy the containers AND the data volumes, then rebuild from nothing
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) up -d --build

# ---------------------------------------------------------------------------
#  Planning
# ---------------------------------------------------------------------------

replan-config:  ## Pick up an edited backend/conf/app.dev.yaml in the planning worker
	$(COMPOSE) restart worker-planning
