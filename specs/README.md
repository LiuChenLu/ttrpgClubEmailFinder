# Specs: planned work, NOT implemented

Everything under `specs/` describes behaviour that **does not exist in the code
yet**. Do not use a spec to learn how the pipeline behaves today; use
[`docs/`](../docs/architecture.md) for that. Iterate on specs freely before
asking an agent to implement them.

## Index

| Spec                                                         | Status              | Summary                                                                                                                            |
| ------------------------------------------------------------ | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| [stage2b_llm_triage/](stage2b_llm_triage/spec.md)            | draft               | LLM labels each rule-kept result by URL and title (page type, institution match) and drops likely non-club or wrong-school results |
| [llm_contact_extraction.md](llm_contact_extraction.md)       | draft, early design | One LLM call per page to identify the school, enumerate clubs and grade contact info per club. Partly out of date; see its header  |
| [query_template_candidates.md](query_template_candidates.md) | draft               | Alternative Stage 1 query templates, kept out of `config/` because the code doesn't read them                                      |

## Header every spec must start with

```
**Status:** draft | accepted | in-progress
**Implements in:** the files that will change or be created
**Docs to update when it lands:** the exact docs/ files and sections that change
```

## Lifecycle

1. **draft**: being iterated on. Anything may change.
2. **accepted**: settled enough to implement.
3. **in-progress**: an agent or you are implementing it.
4. **landed**: the code exists and tests pass. In the same change, update the
   `docs/` files named in the header, then delete the spec (or the part that
   landed). Git history keeps the old text.

If code and a spec disagree, the code is what is true today.
