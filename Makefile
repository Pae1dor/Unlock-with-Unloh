.PHONY: help build up stop down restart logs seed admin

help:
	@echo make build   - build + run
	@echo make up      - run
	@echo make stop    - stop
	@echo make down    - remove containers
	@echo make restart - restart
	@echo make logs    - show app logs
	@echo make seed    - insert sample data
	@echo make admin   - create admin

build:
	docker compose up --build -d

up:
	docker compose up -d
	@echo Running at http://localhost:9999

stop:
	docker compose stop

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f app

seed:
	docker compose exec app python -m app.seed

admin:
	docker compose exec app python -m app.make_admin