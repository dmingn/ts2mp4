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

release:
	echo "Creating a new GitHub release..."
	DATE=$$(date +%Y.%m.%d); \
	LATEST_TAG=$$(git tag -l "$$DATE.*" | sort -V | tail -n 1); \
	N=1; \
	if [ -n "$$LATEST_TAG" ]; then \
		LAST_N=$$(echo "$$LATEST_TAG" | sed 's/.*\.//'); \
		N=$$(expr $$LAST_N + 1); \
	fi; \
	TAG="$$DATE.$$N"; \
	echo "Generated tag: $$TAG"; \
	gh release create "$$TAG" --generate-notes; \
	echo "GitHub release created successfully with tag $$TAG."
