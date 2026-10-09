# 0003. Markdown Leakage Sanitization (Defense in Depth)

## Status

Accepted

## Context

During a processing run for an Islamic lecture transcript, the LLM hallucinated literal backtick characters (`` ` ``) around Quranic verses and Hadith citations. This occurred because the skill's instructions (`tafreegh/SKILL.md`) styled formatting examples using inline Markdown code spans (e.g., `` `(آية)` ``). The global rule demanding English/code isolation via backticks further confused the model, leading it to wrap Arabic citations in literal backticks.

The downstream export script (`export_docx.py`) treated the raw backticks as standard text, writing them directly to the Microsoft Word `<w:t>` XML elements. When rendered in Traditional Arabic, the backtick appears as a high floating comma, introducing an unacceptable artifact.

Per `writing-for-agents`, using a negative constraint (e.g., "NEVER use backticks") steers by prohibition, invoking the "Don't think of an elephant" failure mode, and duplicates behavioral rules into context.

## Decision

1. **Deterministic Sanitization**: The export script (`export_docx.py`) is now the authoritative enforcer (source of truth) for this behavior. It performs targeted regex sanitization stripping backticks only when they enclose Arabic text (`re.sub(r'`([^`]*[\u0600-\u06FF]+[^`]*)`', r'\1', markdown_text)`), preserving legitimate inline backticks around English terms, paths, and identifiers per global isolation rules.
2. **Positive Prompting**: Removed all backtick wrapping from Arabic syntax examples in `tafreegh/SKILL.md`. The prompt should only model the positive, desired output format without relying on negative constraints.

## Consequences

- The export pipeline guarantees clean, artifact-free text in Word documents regardless of underlying LLM quirks or hallucinated code syntax.
- The prompt context load remains lean and avoids the pitfalls of negative steering.
- Requires no retro-cleanup of existing flawed artifacts unless manually initiated, adhering to a forward-only pipeline fix approach.
