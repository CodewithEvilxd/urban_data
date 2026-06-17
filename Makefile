.PHONY: venv install pipeline api seed frontend dev

PYTHON := .venv/Scripts/python
PIP := .venv/Scripts/pip

venv:
	py -3.13 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install: venv
	npm install

pipeline:
	$(PYTHON) scripts/fetch_landsat.py
	$(PYTHON) scripts/calculate_lst.py
	$(PYTHON) ml/train_classifier.py

seed:
	$(PYTHON) api/seed_db.py

api:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	npm run dev

dev: api

demo-setup: pipeline seed
