PY ?= .venv/bin/python

setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[geo,dev]"

data:
	$(PY) scripts/fetch_history.py
	$(PY) scripts/fetch_recent.py
	$(PY) scripts/fetch_forecasts.py
	$(PY) scripts/fetch_rivers.py

train:
	$(PY) scripts/train.py
	$(PY) scripts/train_drought.py
	$(PY) scripts/build_villages.py

score:
	$(PY) scripts/blind_test.py
	$(PY) scripts/posthoc.py

web:
	$(PY) scripts/export_web.py
	$(PY) -m sajag.forecast

serve:
	cd web && python3 -m http.server 8000

test:
	$(PY) -m pytest -q

.PHONY: setup data train score web serve test
