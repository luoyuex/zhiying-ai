.PHONY: up down logs docker-up docker-down docker-logs migrate revision api web test build

up:
	docker compose up -d postgres redis

down:
	docker compose down

logs:
	docker compose logs -f

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

migrate:
	uv run --directory backend alembic upgrade head

revision:
	uv run --directory backend alembic revision --autogenerate -m "$(m)"

api:
	uv run --directory backend uvicorn app.main:app --reload --host 127.0.0.1 --port 8010

web:
	npm --prefix frontend run dev

test:
	uv run --directory backend pytest -q

build:
	npm --prefix frontend run build
