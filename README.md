# ts2mp4

`ts2mp4` is a tool designed to convert Transport Stream (`.ts`) files into Matroska (`.mkv`) format.

## Requirements

`ffmpeg` and `ffprobe` 8.1 or later must be on `PATH`. Older versions do not trim the AAC encoder delay when reading Matroska, which makes the audio quality check fail.

## Development Workflow

### Setup

To install project dependencies:

```bash
uv sync --all-groups
```

### Running Tests and Code Quality Checks

To run all code quality checks and tests:

```bash
make check
```

This command executes:
*   `ruff check .` (linting)
*   `ruff format --check .` (code formatting check)
*   `mypy .` (type checking)
*   `pytest` (unit and integration tests)

For convenience, you can run formatting and all checks at once with the following command:

```bash
make format-and-check
```

### Code Formatting

To format the code using `ruff`:

```bash
make format
```

### Releasing

Package versions come from SemVer git tags (`vMAJOR.MINOR.PATCH`) via hatch-vcs. To publish a GitHub Release, push a matching tag (for example `v1.0.0`). CI creates the release from that tag after checks pass.
