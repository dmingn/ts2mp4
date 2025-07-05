TEST_ASSETS_DIR = tests/assets

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
