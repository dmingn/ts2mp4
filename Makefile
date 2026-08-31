TEST_ASSETS_DIR = tests/assets
TEST_VIDEO_DURATION := 3

.PHONY: all
all: check

.PHONY: sync
sync:
	uv sync --all-groups

.PHONY: check
check: sync $(TEST_ASSETS_DIR)/test_video.ts
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .
	@echo "Running unit tests..."
	uv run pytest --cov=ts2mp4 --cov-fail-under=60 -m unit
	@echo "Running integration tests..."
	uv run pytest --cov=ts2mp4 --cov-fail-under=69 -m integration
	@echo "Running E2E tests..."
	uv run pytest --cov=ts2mp4 -m e2e

.PHONY: format
format: sync
	uv run ruff check . --fix
	uv run ruff format .

.PHONY: format-and-check
format-and-check:
	$(MAKE) format
	$(MAKE) check

$(TEST_ASSETS_DIR)/test_video.ts: Makefile
	@mkdir -p $(TEST_ASSETS_DIR)
	@echo "Generating a $(TEST_VIDEO_DURATION)-second dummy video and audio for testing..."
	ffmpeg \
		-y \
		-f lavfi \
		-i "avsynctest=duration=$(TEST_VIDEO_DURATION)[out0][out1]" \
		-f lavfi \
		-i "sine=frequency=1000:duration=$(TEST_VIDEO_DURATION)" \
		-map 0:v:0 \
		-map 0:a:0 \
		-map 1:a:0 \
		-codec:v mpeg2video \
		-codec:a aac \
		-shortest \
		$@
	@echo "Dummy video '$@' generated successfully."
