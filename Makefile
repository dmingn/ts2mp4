TEST_ASSETS_DIR = tests/assets

.PHONY: check
check: $(TEST_ASSETS_DIR)/test_video.ts
	poetry run black --check .
	poetry run isort --check .
	poetry run flake8 .
	poetry run mypy .
	poetry run pytest --ignore=tests/test_e2e.py
	poetry run pytest tests/test_e2e.py

.PHONY: format
format:
	poetry run isort .
	poetry run black .

$(TEST_ASSETS_DIR)/test_video.ts: Makefile
	@mkdir -p $(TEST_ASSETS_DIR)
	@echo "Generating a 10-second dummy video and audio for testing..."
	ffmpeg \
		-y \
		-f lavfi \
		-i "avsynctest=duration=10[out0][out1]" \
		-codec:a aac \
		$@
	@echo "Dummy video '$@' generated successfully."

.PHONY: release
release:
	@if [ "$(shell git rev-parse --abbrev-ref HEAD)" != "master" ]; then \
		echo "Error: You can only run 'make release' on the master branch."; \
		exit 1; \
	fi
	@echo "Fetching latest from origin/master..."
	@git fetch origin master || { echo "Error: Failed to fetch from origin/master. Please check your network connection or git configuration."; exit 1; }
	@if [ "$(shell git rev-parse HEAD)" != "$(shell git rev-parse origin/master)" ]; then \
		echo "Error: Your local master branch is not up-to-date with origin/master. Please pull the latest changes."; \
		exit 1; \
	fi
	@echo "Getting version from pyproject.toml..."
	$(eval VERSION := $(shell sed -n 's/version = \"\(.*\)\"/\1/p' pyproject.toml))
	@echo "Version: $(VERSION)"
	@echo "Creating git tag $(VERSION)..."
	git tag $(VERSION)
	@echo "Pushing git tag $(VERSION) to origin..."
	git push origin $(VERSION)
