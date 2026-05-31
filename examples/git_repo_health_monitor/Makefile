.PHONY: run clean test help

# Default target
help:
	@echo "Git Repository Health Monitor - Available targets:"
	@echo "  run      - Run the health monitor"
	@echo "  clean    - Remove output files and database"
	@echo "  test     - Run all tests"

# Run the health monitor
run:
	python main.py

# Remove generated files
clean:
	@echo "Cleaning output files, database..."
	rm -f health_report.jsonl health_report.summary.json oref.db
	@echo "Clean complete."

# Remove only the transaction DB
db_clean:
	@echo "Removing transaction database..."
	rm -f oref.db
	@echo "Database cleaned."

# Run all tests
test:
	python -m pytest tests/ -v
