.PHONY: venv install pipeline rebuild-all daily-update refresh-data api seed frontend dev

PYTHON := tools/python312/python
PIP := tools/python312/python -m pip

venv:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

install: venv
	npm --prefix ../frontend install

pipeline:
	$(PYTHON) scripts/fetch_landsat.py
	$(PYTHON) scripts/calculate_lst.py
	$(PYTHON) ml/train_classifier.py

seed:
	$(PYTHON) api/seed_db.py

api:
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	npm --prefix ../frontend run dev

dev: api

demo-setup: pipeline seed

rebuild-all:
	$(PYTHON) scripts/rebuild_all_cities.py

daily-update:
	$(PYTHON) automation/daily_update.py --retrain-model

refresh-data:
	$(PYTHON) scripts/refresh_latest_data.py
