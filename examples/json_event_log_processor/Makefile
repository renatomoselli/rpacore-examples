.PHONY: run clean test help

# Default target
help:
	@echo "JSON Event Log Processor - Available targets:"
	@echo "  run      - Process the committed sample data"
	@echo "  clean    - Remove results, database, and inbox files"
	@echo "  test     - Run all tests"
	@echo "  sample   - Copy sample data to inbox"

# Process the committed sample data.
run:
	python main.py

# Copy sample data to a mutable inbox for a separately configured run.
sample:
	@echo "Copying sample data to inbox/..."
	mkdir -p inbox
	cp sample_data/*.json inbox/
	@echo "Done. Set inbox_dir = \"inbox\" in config.toml to process that copy."

# Remove generated files
clean:
	@echo "Cleaning results/, rpacore.db, and inbox/..."
	rm -rf results/ rpacore.db
	rm -f inbox/*.json
	@echo "Clean complete."

# Run all tests
test:
	python -m pytest tests/ -v
