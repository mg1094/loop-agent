---
name: code-review
description: Review code for correctness, readability, tests, and maintainability.
category: coding
---

Use this skill when the user asks you to review code, a diff, or a pull request.

## Workflow

### 1. Understand the change
- Read the code the user points to.
- Identify the stated or inferred goal of the change.
- Note the programming language, framework, and project conventions.

### 2. Run tests if possible
- If tests exist, run them before reviewing.
- If no tests exist, flag this as a finding.

### 3. Evaluate dimensions

For each significant file or function, check:

- **Correctness**: Does it do what it claims? Are there off-by-one errors, race conditions, or missing validations?
- **Edge cases**: Empty input, malformed input, large input, concurrency, failure paths.
- **Readability**: Naming, function size, comments, complexity.
- **Tests**: Are new behaviors covered? Are tests deterministic and fast?
- **Maintainability**: Duplication, coupling, hard-coded values, magic numbers.
- **Security**: Secrets, injection risks, unsafe file/path access, unsafe eval.
- **Performance**: Obvious inefficiencies, unnecessary I/O, N+1 problems.

### 4. Categorize findings

- **Blocking** — must fix before merge (bugs, security, broken tests).
- **Important** — should fix unless there is a strong reason not to.
- **Nitpick** — style or minor simplification.

### 5. Summarize
- State the overall quality of the change.
- List blocking issues first.
- Offer concrete suggestions, not just complaints.
- Praise good practices when you see them.

## Output format

```
## Summary
Overall judgment and whether it is ready to merge.

## Blocking
- ...

## Important
- ...

## Nitpicks
- ...

## Positive notes
- ...
```

## Constraints

- Be specific: cite file paths and line numbers when possible.
- Do not block on purely stylistic issues unless the project has a clear style guide.
- If you are unsure about a finding, say so.
