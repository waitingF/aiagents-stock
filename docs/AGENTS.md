<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Verification Requirements

After completing any code or behavior changes, agents must run appropriate tests
before handing work back to the user. The verification must demonstrate that:

- The implemented feature or fix behaves as expected.
- Existing functionality that was not intentionally changed still works.
- Any tests that could not be run are clearly reported with the reason.

Prefer targeted tests for the changed area plus the relevant existing regression
suite. For broad or shared changes, also run a wider suite or syntax/import check
when available.
