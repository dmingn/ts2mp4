TEST_ASSETS_DIR = tests/assets
TEST_VIDEO_DURATION := 3

.PHONY: all
all: check

.PHONY: sync
sync:
	uv sync --all-groups

.PHONY: check
check: sync $(TEST_ASSETS_DIR)/test_video.ts $(TEST_ASSETS_DIR)/test_mixed_surround.ts
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy .

	uv run coverage erase
	@echo "Running unit tests..."
	uv run coverage run --append -m pytest -m unit
	@echo "Running integration tests..."
	uv run coverage run --append -m pytest -m integration
	@echo "Running E2E tests..."
	uv run pytest -m e2e

	uv run coverage report

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

$(TEST_ASSETS_DIR)/test_mixed_surround.ts: Makefile
	@mkdir -p $(TEST_ASSETS_DIR)
	@echo "Generating a dummy video whose audio switches from stereo to 5.1ch..."
	ffmpeg \
		-y \
		-f lavfi \
		-i "sine=frequency=1000:sample_rate=48000:duration=$(TEST_VIDEO_DURATION)" \
		-ac 2 \
		-codec:a aac \
		-f adts \
		$@.stereo.aac
	ffmpeg \
		-y \
		-f lavfi \
		-i "sine=frequency=1000:sample_rate=48000:duration=$(TEST_VIDEO_DURATION)" \
		-ac 6 \
		-codec:a aac \
		-f adts \
		$@.surround.aac
	cat $@.stereo.aac $@.surround.aac > $@.mixed.aac
	ffmpeg \
		-y \
		-f lavfi \
		-i "testsrc=size=320x240:rate=30" \
		-i $@.mixed.aac \
		-map 0:v:0 \
		-map 1:a:0 \
		-codec:v mpeg2video \
		-codec:a copy \
		-shortest \
		$@
	rm $@.stereo.aac $@.surround.aac $@.mixed.aac
	@echo "Dummy video '$@' generated successfully."
