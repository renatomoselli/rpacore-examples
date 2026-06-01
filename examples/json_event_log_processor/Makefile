.PHONY: run clean test help

# Default target
help:
	@echo "JSON Event Log Processor - Available targets:"
	@echo "  run      - Copy sample data to inbox and run the processor"
	@echo "  clean    - Remove results, database, and inbox files"
	@echo "  test     - Run all tests"
	@echo "  sample   - Copy sample data to inbox"

# Copy sample data to inbox and run
run: sample
	python main.py

# Copy sample data to inbox
sample:
	@echo "Copying sample data to inbox/..."
	cp sample_data/*.json inbox/
	@echo "Done. Run 'make run' to process."

# Remove generated files
clean:
	@echo "Cleaning results/, rpacore.db, and inbox/..."
	rm -rf results/ rpacore.db
	rm -f inbox/*.json
	@echo "Clean complete."

# Run all tests
test:
	python -m pytest tests/ -v
