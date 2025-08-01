# AGENTS.md - Project Guide for AI Agents

This file provides guidelines and context for AI agents (like me) working on the `ts2mp4` project.

For general project information, including project overview, technology stack, project structure, and development workflow, please refer to `README.md`.

### Referencing Guidelines

*   When referencing or applying guidelines from this `AGENTS.md` file, the agent will explicitly state that it is doing so in the conversation.

## 1. Coding Guidelines

### 1.1. Code Style

*   Follow the style of the existing codebase (indentation, naming conventions, etc.).

### 1.2. Comments and Docstrings

*   Write comments and docstrings in English. This rule applies regardless of the user's interaction language.

### 1.3. File Endings

*   Ensure all files end with a single newline character.

### 1.4. Verification

*   Always run existing tests before making changes to ensure no regressions.

### 1.5. Makefile Usage

*   Prioritize using commands defined in the `Makefile` if available.

## 2. Git Guidelines

### 2.1. Branch Naming

*   When creating new branches for features, bug fixes, or other tasks, use descriptive prefixes such as `feature/`, `bugfix/`, or `hotfix/` (e.g., `feature/add-new-cli-command`).

### 2.2. Commit Message Creation

#### 2.2.1. Diff-based Content

*   Focus solely on the changes being committed. Disregard the agent's conversation history.
*   Ensure every point in the proposed commit message directly corresponds to a visible change in the *diff of the changes being committed*. This typically means `git diff --staged` for staged changes, or `git diff HEAD` for unstaged changes if committing with `-a`. Do not include information not explicitly present in that diff.

#### 2.2.2. Formatting

*   When using `git commit -m`, always enclose the entire commit message in single quotes to prevent shell interpretation of inline code blocks or special characters.

#### 2.2.3. Language

*   Commit messages must be written in English. This rule applies regardless of the user's interaction language.

### 2.3. Commit Failures

*   If a commit operation fails, especially due to issues with multi-line strings or special characters in the commit message (even when enclosed in single quotes), try the following workaround:
    1.  Write the desired commit message to `.git/COMMIT_EDITMSG`.
    2.  Execute `git commit -F .git/COMMIT_EDITMSG` to apply the commit message from the file.
    3.  If the original issue persists or a new one emerges, inform the user about the failure and await guidance.

## 3. Interaction

### 3.1. Interaction Language

*   The agent will adapt its communication language to match the language used by the user in the current conversation.

## 4. Debugging Principles

### 4.1. Test Failure Debugging Principle

*   When a test fails, **prioritize factual problem isolation over speculative cause analysis**. Do not attempt to fix based on assumptions. Instead, systematically gather concrete evidence from the failing environment to pinpoint the exact point of failure and its direct cause. This involves:
    1.  **Literal Interpretation of Error Messages**: Understand what the error message *literally* states, without adding unverified interpretations.
    2.  **Verification of Assumptions**: If an assumption is made (e.g., "file exists"), programmatically verify it within the context where the failure occurs (e.g., inside a subprocess).
    3.  **Systematic Isolation**: Use debugging techniques (e.g., temporary logging, conditional breakpoints) to narrow down the problem to the smallest possible scope.
    4.  **Avoid Premature Solutions**: Do not propose or implement solutions until the root cause is definitively identified through factual evidence.
