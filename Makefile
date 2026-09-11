COMPOSE_FILES := -f docker-compose.yml

ifneq ($(wildcard .compose.codex-local.yml),)
COMPOSE_FILES += -f .compose.codex-local.yml
endif

.PHONY: app.up back.up front.up

app.up: back.up front.up

back.up:
	docker compose $(COMPOSE_FILES) up --build -d

front.up:
	@test -x frontend/node_modules/.bin/vite || npm --prefix frontend install
	npm --prefix frontend run dev
