
-include .env
export

PY ?= .venv/bin/python
PORT ?= 8000
EXPORT ?= $(HOME)/Downloads/algeria-fire-map-data/detections.csv
EXPORT_DIR ?= data/algeria-fire-map-data

.PHONY: help setup dev api dashboard-dev dashboard-build test lint fmt check-columns train train-dza train-dza-nowind evaluate crossval replay-ai export model data import-export static-raster firms-live lan-ip demo-check docker-up docker-down docker-logs

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup:           ## create .venv (Python 3.11) and install everything
	python3.11 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt
	@test -f .env || cp .env.example .env
	@echo "ok: now run 'make api'"

dev:             ## API (:8000) + dashboard (:5173) together with hot reload (needs .venv and `npm ci`)
	npx turbo dev

api:             ## run the API + dashboard + phone page on the LAN
	$(PY) -m uvicorn api.main:app --host 0.0.0.0 --port $(PORT) --reload

dashboard-dev:   ## dashboard only, hot reload on :5173 (proxies the API on :8000; run `make api` too)
	npm install && npm run dev --workspace dashboard

dashboard-build: ## build dashboard/dist/, which `make api` serves at /dashboard/
	npm ci && npm run build --workspace dashboard

test:            ## all smoke tests
	$(PY) -m pytest -q

lint:            ## ruff
	$(PY) -m ruff check .

fmt:             ## ruff autofix
	$(PY) -m ruff check . --fix

check-columns:   ## inspect data/out/train.parquet against config.yaml
	$(PY) -m model.check_columns

train:           ## model C, mixed (all countries)
	$(PY) -m model.train

train-dza:       ## model C, Algeria only (for the comparison)
	$(PY) -m model.train --countries DZA --tag dza

train-dza-nowind: ## model C, Algeria only, no wind features (wind-scenario blend)
	$(PY) -m model.train --countries DZA --tag dza --no-wind

evaluate:        ## thresholds + scoreboard on held-out fires
	$(PY) -m model.evaluate

crossval:        ## every Algerian year tested once (B tuned on all vs DZA, and C)
	$(PY) -m model.crossval

replay-ai:       ## model C's advice on the replays (#52): zones + times next to B, never alerts
	$(PY) -m model.replay_ai

export:          ## publish artifacts for the API (TAG=mixed to ship C)
	$(PY) -m model.export $(if $(TAG),--tag $(TAG),)

model: train train-dza train-dza-nowind evaluate crossval replay-ai   ## full model loop

data:            ## run the firedata pipeline (laptop only; see data/README.md)
	cd data/firedata && export FIREDATA_DIR=.. && ../../$(PY) 01_download_firms.py \
	  && ../../$(PY) 02_clean.py --export $(EXPORT) \
	  && ../../$(PY) 03_weather.py && ../../$(PY) 04_terrain_fuel.py && ../../$(PY) 05_build_table.py

import-export:   ## real data for the API from the Algeria Fire Map export (EXPORT_DIR=...)
	cd data/firedata && FIREDATA_DIR=.. ../../$(PY) import_export.py --export-dir $(abspath $(EXPORT_DIR))

static-raster:   ## terrain + fuel at 375 m for northern Algeria -> data/out/static_375m.npz (#17; resumable, network)
	$(PY) data/build_static_raster.py

firms-live:      ## fetch the newest FIRMS detections once into data/live/ (needs FIRMS_MAP_KEY in .env)
	$(PY) -m api.firms_live

docker-up:       ## build and start the whole demo in Docker (API + dashboard + phone page) on :$(PORT)
	@mkdir -p data/out data/live model/artifacts
	docker compose up -d --build

docker-down:     ## stop and remove the demo container
	docker compose down

docker-logs:     ## follow the API container logs
	docker compose logs -f api

lan-ip:          ## the address test phones should open
	@echo "phones: http://$$(hostname -I 2>/dev/null | awk '{print $$1}' || ipconfig getifaddr en0):$(PORT)/alert/"

demo-check:      ## issue #16: 5 timed runs, AI flag → approve → phone stream (API must be running)
	.venv/bin/python scripts/demo_check.py --base http://localhost:$(PORT)
