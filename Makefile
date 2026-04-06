.PHONY: setup run server inference test docker clean

# One command to rule them all: install deps, start server, run inference
run: setup
	@echo ""
	@echo "Starting environment server on http://localhost:7860 ..."
	@python3 -m server.app &
	@sleep 2
	@echo ""
	@echo "Running inference against all 3 tasks..."
	@echo ""
	@python3 inference.py
	@echo ""
	@echo "Shutting down server..."
	@-kill %1 2>/dev/null

# Install all dependencies + create .env if missing
setup:
	@echo "Installing dependencies..."
	@pip3 install -r requirements.txt -q
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — edit it to add your HF_TOKEN"; \
	fi
	@echo "Done."

# Start just the server (for manual testing)
server:
	python3 -m server.app

# Run just the inference script (assumes server is already running)
inference:
	python3 inference.py

# Run all tests
test: setup
	@python3 -m pytest tests/ -v

# Build and run with Docker
docker:
	docker build -t incident-response-env .
	docker run -p 7860:7860 incident-response-env

# Clean up
clean:
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
