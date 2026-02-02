PYTHON := python3
PIP := $(PYTHON) -m pip

SRC_DIR := src
TEST_DIR := tests

.PHONY: all
all: test lint coverage

.PHONY: test
test: install-deps
	@echo "Running pytest with coverage..."
	$(PYTHON) -m pytest -v --cov=$(SRC_DIR) --cov-report=term-missing $(TEST_DIR)

.PHONY: install-deps
install-deps:
	@echo "Installing dev/test dependencies..."
	$(PIP) install --upgrade pip
	$(PIP) install ".[testing]"

.PHONY: lint
lint:
	black --check $(SRC_DIR) $(TEST_DIR)
	mypy $(SRC_DIR)

.PHONY: format
format:
	black $(SRC_DIR) $(TEST_DIR)

.PHONY: coverage
coverage:
	$(PYTHON) -m pytest --cov=$(SRC_DIR) --cov-report=html $(TEST_DIR)

.PHONY: clean
clean:
	find $(SRC_DIR) $(TEST_DIR) -type d -name "__pycache__" -exec rm -rf {} +
	rm -f .coverage
	rm -rf htmlcov build dist *.egg-info
