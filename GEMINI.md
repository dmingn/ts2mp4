# GEMINI.md - Project Guide for AI Agents

This file provides guidelines and context for AI agents (like me) working on the `ts2mp4` project.

## 1. Project Overview

`ts2mp4` is a tool designed to convert Transport Stream (`.ts`) files into MP4 format.

## 2. Technology Stack

*   **Language**: Python
*   **Package Management**: Poetry
*   **Testing Framework**: pytest
*   **Linters**: flake8, mypy

## 3. Project Structure

*   `ts2mp4/`: Main source code.
    *   `__main__.py`: CLI entry point.
    *   `ts2mp4.py`: Core conversion logic.
    *   `cli.py`: Command-line interface definition.
    *   `audio_integrity.py`: Audio integrity check related logic.
*   `tests/`: Project tests.
*   `pyproject.toml`: Poetry project configuration and dependencies.
*   `Makefile`: Shortcuts for common development tasks.

## 4. Development Workflow

### 4.1. Setup

To install project dependencies:

```bash
poetry install
```

### 4.2. Running Tests

Execute tests using `pytest`:

```bash
poetry run pytest
```

### 4.3. Code Quality Checks

To run all code quality checks and tests:

```bash
make check
```

This command executes:
*   `black --check .` (code formatting)
*   `isort --check .` (import sorting)
*   `flake8 .` (linting)
*   `mypy .` (type checking)
*   `pytest` (unit and integration tests)

Alternatively, you can run individual checks:

*   **Linting (flake8)**:
    ```bash
    poetry run flake8 .
    ```
*   **Type Checking (mypy)**:
    ```bash
    poetry run mypy .
    ```

## 5. Coding Standards

*   Adhere to PEP 8.
*   Follow the style of the existing codebase (indentation, naming conventions, etc.).
*   Actively use type hints.
*   Write comments in English.
*   Ensure all files end with a single newline character.

## 6. Git Workflow

*   When creating new branches for features, bug fixes, or other tasks, use descriptive prefixes such as `feature/`, `bugfix/`, or `hotfix/` (e.g., `feature/add-new-cli-command`).

## 7. Important Considerations for AI Agents

*   **Common Tasks**: AI agents are expected to perform tasks such as bug fixes, implementing new features, refactoring existing code, adding/updating tests, and updating documentation.
*   **Verification**: Always run existing tests before making changes to ensure no regressions.
*   **Dependencies**: If adding new dependencies, ensure `pyproject.toml` and `poetry.lock` are updated.
*   **Makefile Usage**: Prioritize using commands defined in the `Makefile` if available.
*   **Interaction Language**: The Gemini CLI will adapt its communication language to match the language used by the user in the current conversation.
*   **Commit Failures**: If a commit operation fails, especially due to issues with multi-line strings in the commit message, try the following workaround:
    1.  Write the desired commit message to `.git/COMMIT_EDITMSG`.
    2.  Execute `git commit -F .git/COMMIT_EDITMSG` to apply the commit message from the file.
    3.  If the issue persists or is different, inform the user about the failure and await guidance.
*   **Commit Message Creation**: When crafting commit messages, focus solely on the staged diff. Disregard the Gemini CLI conversation history, as the commit message should accurately reflect the changes introduced by the commit itself. **Always run `git diff --staged` before proposing a commit message to ensure it accurately reflects only the staged changes.**
*   **Test Failure Debugging Principle**: When a test fails, **prioritize factual problem isolation over speculative cause analysis**. Do not attempt to fix based on assumptions. Instead, systematically gather concrete evidence from the failing environment to pinpoint the exact point of failure and its direct cause. This involves: 
    1.  **Literal Interpretation of Error Messages**: Understand what the error message *literally* states, without adding unverified interpretations.
    2.  **Verification of Assumptions**: If an assumption is made (e.g., "file exists"), programmatically verify it within the context where the failure occurs (e.g., inside a subprocess).
    3.  **Systematic Isolation**: Use debugging techniques (e.g., temporary logging, conditional breakpoints) to narrow down the problem to the smallest possible scope.
    4.  **Avoid Premature Solutions**: Do not propose or implement solutions until the root cause is definitively identified through factual evidence.
