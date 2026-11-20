-include .env
export

PY ?= .venv/bin/python
PORT ?= 8000

.PHONY: help setup api test lint fmt check-columns train train-dza evaluate export model data lan-ip

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

setup:           ## create .venv (Python 3.11) and install everything
	python3.11 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt
	@test -f .env || cp .env.example .env
	@echo "ok: now run 'make api'"

api:             ## run the API + dashboard + phone page on the LAN
	$(PY) -m uvicorn api.main:app --host 0.0.0.0 --port $(PORT) --reload

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

evaluate:        ## thresholds + scoreboard on held-out fires
	$(PY) -m model.evaluate

export:          ## publish artifacts for the API (TAG=mixed to ship C)
	$(PY) -m model.export $(if $(TAG),--tag $(TAG),)

model: train train-dza evaluate   ## full model loop

data:            ## run the firedata pipeline (laptop only; see data/README.md)
	cd data && ../$(PY) 01_download_firms.py && ../$(PY) 02_clean.py --export detections.csv \
	  && ../$(PY) 03_weather.py && ../$(PY) 04_terrain_fuel.py && ../$(PY) 05_build_table.py

lan-ip:          ## the address test phones should open
	@echo "phones: http://$$(hostname -I 2>/dev/null | awk '{print $$1}' || ipconfig getifaddr en0):$(PORT)/alert/"
