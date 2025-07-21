# ts2mp4

`ts2mp4` is a tool designed to convert Transport Stream (`.ts`) files into MP4 format.

## Project Structure

*   `ts2mp4/`: Main source code.
    *   `__main__.py`: CLI entry point.
    *   `ts2mp4.py`: Core conversion logic.
    *   `cli.py`: Command-line interface definition.
    *   `audio_reencoder.py`: Audio re-encoding logic.
    *   `ffmpeg.py`: Wrapper for `ffmpeg` and `ffprobe` commands.
    *   `hashing.py`: File hashing utilities.
    *   `media_info.py`: Media file information retrieval.
    *   `quality_check.py`: Post-conversion quality checks.
    *   `stream_integrity.py`: Audio and video stream integrity checks.
*   `tests/`: Project tests.
*   `pyproject.toml`: Poetry project configuration and dependencies.
*   `Makefile`: Shortcuts for common development tasks.

## Development Workflow

### Setup

To install project dependencies:

```bash
poetry install
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
