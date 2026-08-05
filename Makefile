.PHONY: help install test demo reports dashboard serve check clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## install dependencies
	pip install -r requirements.txt

test:  ## run the test suite (no API key needed)
	BEDTIME_PROVIDER=mock python -m pytest tests/ -q

demo:  ## offline end-to-end story
	BEDTIME_PROVIDER=mock python main.py "A story about a girl named Alice and her best friend Bob, who happens to be a cat."

reports:  ## regenerate all three reports
	python -m bedtime.evaluation.calibrate
	python -m bedtime.evaluation.run_eval
	python -m bedtime.evaluation.red_team

reports-mock:  ## regenerate reports offline (smoke test only)
	python -m bedtime.evaluation.calibrate --mock
	python -m bedtime.evaluation.run_eval --mock
	python -m bedtime.evaluation.red_team --mock

seed:  ## load the 10-story library into memory
	python -m bedtime.library.seed

seed-check:  ## gate the seed library without indexing
	python -m bedtime.library.seed --check

web:  ## run the Streamlit site
	streamlit run app.py

web-demo:  ## run the site in offline mock mode
	BEDTIME_PROVIDER=mock streamlit run app.py

audio:  ## generate a story and read it aloud
	python main.py --audio "A story about a girl named Alice and her best friend Bob, who happens to be a cat."

dashboard:  ## build the HTML monitoring dashboard
	python -m bedtime.observability.dashboard

serve:  ## run the API on :8000
	uvicorn bedtime.api:app --host 0.0.0.0 --port 8000

check:  ## CI gate: tests + secret scan + red team
	@echo "--- secret scan ---"
	@! grep -rInE 'sk-[A-Za-z0-9_-]{20,}' --include='*.py' --include='*.md' --include='*.txt' --include='*.json' \
		--exclude-dir='_interview_prep' --exclude-dir='.git' . \
		|| (echo "API KEY FOUND - do not commit" && exit 1)
	@echo "clean"
	@$(MAKE) test
	@echo "--- every module imports ---"
	@python -c "import glob, importlib; \
		mods = [p[:-3].replace('/', '.') for p in glob.glob('bedtime/**/*.py', recursive=True) if '__init__' not in p]; \
		[importlib.import_module(m) for m in mods]; \
		import main; print(f'{len(mods)} modules ok')"
	python -m bedtime.library.seed --check
	BEDTIME_PROVIDER=mock python -m bedtime.evaluation.red_team --mock --strict-exit

clean:
	rm -rf traces/ reports/*.html __pycache__ .pytest_cache
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
