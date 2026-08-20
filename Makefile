# Test framework entry points.
#
# Everything runs through the repo-root virtualenv. Homebrew's Python is
# PEP 668 externally-managed, so a bare `pip` install fails — see README.

VENV    := .venv
PY      := $(VENV)/bin/python
PYTEST  := $(VENV)/bin/pytest
RESULTS := reports/allure-results
REPORT  := reports/allure-report

# Extra pytest arguments: make smoke ARGS="-n 4"
ARGS ?=

.PHONY: install smoke api ui db all regression destructive report report-static clean help

help:
	@echo "make install    create the venv and install test dependencies"
	@echo "make smoke      fast critical-path gate"
	@echo "make api        API suite, 4 workers"
	@echo "make ui         browser suite, 2 workers"
	@echo "make db         database assertions (needs TEST_DATABASE_URL, else skips)"
	@echo "make all        everything, 4 workers"
	@echo "make report     open the Allure report"
	@echo "make clean      wipe reports"
	@echo ""
	@echo "Pass extra arguments with ARGS, e.g. make smoke ARGS=\"-n 4\""

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r tests/requirements-test.txt

# Results are cleared before each run. Allure appends, so without this a report
# shows tests that passed two runs ago alongside today's failures.
smoke:
	@rm -rf $(RESULTS)
	$(PYTEST) -m smoke $(ARGS)

api:
	@rm -rf $(RESULTS)
	$(PYTEST) -m api -n 4 $(ARGS)

ui:
	@rm -rf $(RESULTS)
	$(PYTEST) -m ui -n 2 $(ARGS)

# Skips cleanly with TEST_DATABASE_URL unset, which is the point — see
# TEST_STRATEGY.md §9.
db:
	@rm -rf $(RESULTS)
	$(PYTEST) -m db $(ARGS)

all:
	@rm -rf $(RESULTS)
	$(PYTEST) -n 4 $(ARGS)

regression:
	@rm -rf $(RESULTS)
	$(PYTEST) -m "not destructive" -n 4 $(ARGS)

# Exclusive database state, so never in parallel.
destructive:
	$(PYTEST) -m destructive $(ARGS)

# Both report targets say what they are about to include first. A report is a
# snapshot of the results directory at the moment it is generated, and a run
# that finishes afterwards is silently absent from it — which is how a whole
# browser job once went missing from a report that looked complete.
define summarise_results
	@echo "Including $$(ls $(RESULTS)/*-result.json 2>/dev/null | wc -l | tr -d ' ') result file(s), newest written $$(ls -t $(RESULTS)/*-result.json 2>/dev/null | head -1 | xargs -I{} date -r {} '+%H:%M:%S' 2>/dev/null || echo 'never')."
endef

report:
	$(summarise_results)
	allure serve $(RESULTS)

# Generates to disk instead of serving — what CI publishes.
report-static:
	$(summarise_results)
	allure generate $(RESULTS) --clean -o $(REPORT)
	@$(PY) tests/utils/verify_report.py $(RESULTS) $(REPORT)

clean:
	rm -rf reports .pytest_cache
	find tests -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
