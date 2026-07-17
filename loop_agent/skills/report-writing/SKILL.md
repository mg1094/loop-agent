---
name: report-writing
description: Produce structured, sourced reports with executive summary, findings, and recommendations.
category: writing
---

Use this skill when the user asks for a report, memo, brief, or structured analysis.

## Workflow

### 1. Define scope
- Determine the report's purpose, audience, length, and deadline tone.
- Agree on the key questions the report must answer.
- Identify whether the user wants a short memo (< 1 page) or a full report.

### 2. Gather evidence
- Use `web_search` or `read_file` as needed.
- Record sources with URLs, titles, and dates.
- Distinguish verified facts from inference or assumption.

### 3. Outline
- Executive Summary
- Background / Context
- Methodology (how you gathered and evaluated information)
- Findings (bulleted or numbered, each supported by evidence)
- Recommendations or Conclusion
- Sources / Appendix

### 4. Draft
- Write the Executive Summary first; it should stand alone.
- Use headings and bullets to make the report scannable.
- Include inline citations like "(Source: example.com, 2026-07-11)".
- Keep paragraphs short. One idea per paragraph.

### 5. Review
- Check that every finding is supported by a source.
- Verify the Executive Summary matches the detailed findings.
- Remove jargon that the audience would not understand.
- Ensure recommendations are actionable and tied to findings.

## Output format

```
# <Report Title>

## Executive Summary
1-3 paragraphs with the answer, key numbers, and main recommendation.

## Background
Why this question matters.

## Findings
- Finding 1 (Source: ...)
- Finding 2 (Source: ...)

## Recommendations
1. ...
2. ...

## Sources
- Title, URL, date
```

## Constraints

- Never invent data, quotes, or URLs.
- If a critical source is missing, say so and note the gap.
- Keep the report focused on the original question.
