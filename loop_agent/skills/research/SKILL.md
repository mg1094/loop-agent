---
name: research
description: Investigate a topic, gather evidence, and synthesize a sourced answer.
category: research
---

## Workflow

Load this skill before starting any research task.

### 1. Clarify the question
- Restate the user's question in your own words.
- Identify the scope (time period, geography, domain).
- Flag any ambiguous terms and ask for clarification if the answer would change materially.

### 2. Decompose
- Break the question into 2-5 concrete sub-questions.
- Prioritize sub-questions by importance and uncertainty.

### 3. Gather evidence
- Use `web_search` for public facts, recent events, and official sources.
- Use `read_file` for local documents or prior session context.
- Prefer primary sources (official docs, papers, reports) over random blogs.
- For each source, record: title, URL, date retrieved, and the specific claim it supports.

### 4. Evaluate
- Cross-check claims across multiple sources when possible.
- Note conflicts, outdated information, or low-confidence facts.
- Use phrases like "according to X", "X reports that", "no public source confirms".

### 5. Synthesize
- Answer the original question directly.
- Cite sources inline or in a Sources section.
- State your confidence level (high / medium / low) and why.

## Output format

1. **Summary** — 1-3 sentence direct answer.
2. **Key findings** — bullet list with inline citations.
3. **Sources** — list of URLs/documents with dates.
4. **Confidence and caveats** — what is uncertain or missing.

## Constraints

- Do not invent facts, URLs, or quotations.
- If search returns no useful results, say so explicitly.
- Distinguish between facts, inference, and opinion.
