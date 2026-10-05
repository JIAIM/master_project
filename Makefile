.PHONY: up down logs migration migrate test shell

up:            
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f backend

migration:     
	docker compose run --rm backend alembic revision --autogenerate -m "$(m)"

migrate:
	docker compose run --rm backend alembic upgrade head

test:
	docker compose run --rm backend sh -c "pip install -q pytest && python -m pytest -v"

shell:
	docker compose exec backend bash
