---
name: coding
description: Write, review, and run code with a structured plan-test-explain workflow.
category: coding
---

## Workflow

Before writing any code, load this skill and follow the steps below.

### 1. Understand the request
- Restate the goal in one sentence.
- Identify inputs, outputs, edge cases, and constraints.
- Ask the user to clarify ambiguities before proceeding.

### 2. Explore the codebase
- Use `read_file` to inspect relevant existing files.
- Check `pyproject.toml`, `README.md`, or nearby modules for conventions.
- Look for existing tests you can mimic.

### 3. Plan
- Briefly explain your approach (algorithm, data structures, public API).
- If the change is large, outline the files you will create or modify.
- Get implicit or explicit agreement if the user might prefer a different design.

### 4. Implement
- Write minimal, correct code first; optimize later only if needed.
- Follow existing naming and style in the project.
- Add type hints where the codebase already uses them.
- Add short, useful comments only when the code is not self-explanatory.
- Never commit secrets or hard-coded credentials.

### 5. Test
- Prefer running existing tests with the user's test runner.
- If no tests exist, suggest or write focused unit tests for the new behavior.
- Report the test result and fix regressions before finishing.

### 6. Explain
- Summarize what changed and why.
- Mention any trade-offs, limitations, or follow-up work.
- Tell the user how to run or verify the result.

## Output format

For code changes, structure your final response as:

1. **What changed** — one-paragraph summary.
2. **Files touched** — list with one-line purpose each.
3. **How to verify** — exact command to run or test.
4. **Notes / trade-offs** — optional caveats.

## Error handling

- If a tool call fails, report the exact error and ask whether to retry, skip, or change approach.
- Do not silently ignore failures.
- Keep the user informed when a step takes more than a few iterations.
