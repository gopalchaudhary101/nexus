.PHONY: install demo seed test lint typecheck web-install web-build up down clean

install:            ## Install backend deps
	pip install -r apps/api/requirements.txt

demo: demo-data seed   ## Generate synthetic demo data + seed demo user
.PHONY: demo-data

demo-data:          ## Generate the synthetic demo dataset (no real personal data)
	python3 scripts/generate_demo_data.py

seed:               ## Create demo user + ingest demo data (demo@nexus.local)
	python3 scripts/seed_demo.py

test:               ## Run backend tests
	python3 -m pytest

lint:               ## Ruff check
	ruff check ml apps/api tests scripts

typecheck:          ## mypy (backend)
	mypy ml apps/api/app --ignore-missing-imports

web-install:        ## Install frontend deps
	cd apps/web && npm install

web-build:          ## Type-check + production build
	cd apps/web && npm run build

up:                 ## Docker Compose (requires Docker)
	docker compose up --build

down:
	docker compose down

clean:
	rm -rf data/processed
