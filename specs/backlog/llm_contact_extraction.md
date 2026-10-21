# Proposal: LLM Relevance Assessment for the Club-Finding Pipeline

**Status:** draft, early design. **Nothing in this file is implemented.** It was
written before the pipeline was split into Stages 0 to 4 and before the Stage 2b
triage spec, so the pipeline diagram and cost numbers (6,000 schools, 3 queries)
are out of date. **Scope:** v1 — single model, single combined call, no cascade
**Implements in:** a new stage after `render_candidates.py`; would replace or
extend `extract_contact_info.py`. **Docs to update when it lands:**
`docs/architecture.md`, `docs/data_flow.md` (new CSV columns),
`docs/stages/stage4_extract_contact_info.md`. **Related:**
[stage2b_llm_triage/spec.md](stage2b_llm_triage/spec.md) is a separate, cheaper
LLM step that only reads URL and title.

## Summary

Add an LLM assessment step between search results and final CSV output. Each
candidate URL from the search pipeline gets sent to Gemini 2.5 Flash once, which
identifies the school, enumerates every club described on the page (zero, one,
or many), and assesses contact info per club — instead of relying on the search
engine's own relevance score, and instead of separate classify/extract passes.

## Why

Three things we've confirmed about the current pipeline:

1. **Search relevance scores aren't a reliable filter.** Pages that are the
   correct answer have shown up scored low, and pages from the wrong institution
   have outranked correct ones. The engine's score isn't a trustworthy gate on
   its own.
2. **String/domain matching can't resolve school identity reliably.** Club pages
   are often off the school's official domain (engagement platforms, Discord,
   social), and schools are referred to by abbreviations or local nicknames
   ("UConn," "CT State Manchester") that aren't reliably listed anywhere
   programmatically accessible. This needs judgment, not a lookup table.
3. **Pages aren't one-club-per-page.** Some schools list every club on a single
   page (no individual club pages at all), and some of those shared listings
   also share a single generic contact mechanism (e.g. one "Contact Us" button
   on a CampusGroups-style page, reused across unrelated clubs). The output
   needs to represent zero, one, or many clubs per page, with contact confidence
   graded per club — not assumed uniform across a page.

An LLM with the page content and the school name can reason about all three —
general knowledge of institution names plus corroborating page evidence,
enumerating however many distinct clubs actually appear, and judging whether a
contact signal is specific to one club or just page-wide — in a way string
matching and fixed single-object extraction can't.

## Approach

**Model:** `gemini-2.5-flash`, single tier, one call per candidate URL. No
confidence-based escalation to a second model in v1 — if this proves
insufficient on hard cases, that's a fast follow-up, not a day-one requirement.

**One combined call, not classify-then-extract.** Earlier drafts of this
proposal considered a two-step split (classify the page, then only extract
contact info if it's confirmed a club page). That made sense when "conglomerate"
meant "nothing to extract." It doesn't anymore: conglomerate pages are exactly
where multi-club extraction happens, so gating extraction behind a separate
classification call would mean paying to re-read the same page twice for no
benefit. Structuring the response as an array of club entries gets
classification for free — array length of 0 / 1 / many _is_ the category —
without asking the model to name a category explicitly or juggle conditional
fields.

**Schema:**

```python
from pydantic import BaseModel
from typing import Optional

class ClubEntry(BaseModel):
    club_name: str
    contact_signal_tier: str        # "direct" | "shared" | "none"
    email_found: bool
    discord_found: bool
    contact_signal_snippet: Optional[str]

class PageAssessment(BaseModel):
    school_match: bool
    school_match_confidence: str    # "low" | "medium" | "high"
    school_identifying_terms_found: Optional[str]
    clubs: list[ClubEntry]          # empty = neither, one = club page, many = conglomerate
```

- `school_match_confidence` carries the identity-resolution risk from
  abbreviations/nicknames — low confidence routes to review rather than being
  trusted outright (see pipeline diagram below).
- `contact_signal_tier` is graded, not boolean, specifically to catch the
  CampusGroups failure mode: a single generic contact widget shared across many
  listed clubs must not be recorded as "direct" contact for all of them. The
  prompt instructs the model explicitly to distinguish a mechanism specific to
  one club's listing ("direct") from one that's page-wide/generic ("shared") —
  this is the main new risk this design introduces, and the one most worth
  checking in validation.
- `school_identifying_terms_found` is a free byproduct — logging what term
  actually confirmed the match (an abbreviation, a domain, etc.) builds toward a
  future alias reference without dedicated effort now.
- `email_found` and `contact_signal_snippet` are built to resist a different
  failure mode: a model asked to "find the email" can reconstruct a
  plausible-looking address that isn't actually present — a wrong domain guess,
  an invented local-part — rather than report what's genuinely on the page. The
  prompt requires `contact_signal_snippet` to be copied verbatim from the page
  content, never normalized or reconstructed, and requires
  `email_found`/`discord_found` to be `false` whenever the model isn't confident
  a genuine pattern (including obfuscated forms like "name at school dot edu")
  is actually present, rather than guessing. This gives a raw, human-verifiable
  span instead of a cleaned-up value that has to be trusted blindly.

**Reference implementation:**

```python
from google import genai

client = genai.Client(api_key=GEMINI_API_KEY)

def assess_page(school_name: str, page_content: str) -> PageAssessment:
    prompt = f"""School: {school_name}

Page content:
{page_content[:4000]}

Identify whether this page is about this specific school — the school may be
referred to by its official name, a common abbreviation (e.g. "UConn" for
University of Connecticut), or a local nickname not found in general
reference sources. Use general knowledge of the school plus corroborating
evidence on the page (email domain, address, affiliated links), not just a
literal name match.

List every distinct tabletop RPG, D&D, or gaming club described on the page —
there may be none, one, or many (some schools list all clubs on one shared
page). For each club, note whether an email or Discord contact was found, and
grade the contact signal as:
- "direct": contact info specific to this club's own listing
- "shared": a single generic contact mechanism reused across many unrelated
  clubs on the same page (e.g. one page-wide "Contact Us" button) — do not
  report this as "direct" for every club just because it's the only contact
  method visible on the page
- "none": no contact info found for this club

For any contact information you report, copy the exact text verbatim from
the page content into contact_signal_snippet — do not normalize, clean up,
or reconstruct it, including obfuscated forms like "name at school dot edu".
If you are not confident a genuine email or Discord pattern is actually
present in the text, set email_found/discord_found to false rather than
guessing a plausible-looking address."""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": PageAssessment,
        },
    )
    return response.parsed
```

## CSV output

The model's job stops at producing the structured assessment; flattening to CSV
rows is plain code, not another model call. One page becomes zero, one, or many
rows:

```python
rows = []
if result.school_match and result.school_match_confidence != "low":
    for club in result.clubs:
        rows.append({
            "university_name": school_name,                       # known input, not re-derived
            "club_name": club.club_name,
            "contact_signal_tier": club.contact_signal_tier,
            "email_found": club.email_found,
            "discord_found": club.discord_found,
            "contact_signal_snippet": club.contact_signal_snippet,
            "result_url": url,                                     # one value, same for every row from this page
            "school_identifying_terms_found": result.school_identifying_terms_found,
        })
```

Columns:
`university_name, club_name, contact_signal_tier, email_found, discord_found, contact_signal_snippet, result_url, school_identifying_terms_found`.

- A conglomerate page naturally produces multiple rows, one per club found.
- The same club found at two different URLs naturally produces two rows, since
  each page is assessed independently and `result_url` is carried straight
  through — no dedup logic needed at this stage.

## Where this sits in the pipeline

```
Tavily search/crawl results (per school)
        │
        ▼
  LLM assessment (combined call)   ← this proposal
        │
   ┌────┴─────────────┐
   ▼                   ▼
school_match true    school_match false,
+ confidence ok       or confidence low
        │                   │
        ▼                   ▼
  flatten clubs[]      review queue
  → CSV rows           (not discarded,
                         not auto-escalated
                         to a 2nd model)
```

Low-confidence identity matches go to a lightweight human review queue rather
than being silently included or dropped. This is the one piece of hard-case
handling kept in v1 — cheap (just routing, no new model call) and prevents
genuinely ambiguous identity cases from polluting the CSV or vanishing.

## Cost estimate

Worst-case volume: 6,000 schools × 3 queries × 10 results, all unique =
**180,000 calls**.

Conservative estimate: \~2,000 input tokens (page content + prompt + schema) and
\~200 output tokens per call for a typical single-club or empty page → 360M
input / 36M output tokens total.

| Mode                                           | Rate                   | Total     |
| ---------------------------------------------- | ---------------------- | --------- |
| Batch (recommended — you can run this offline) | $0.15 / $1.25 per MTok | **≈ $99** |
| Standard/synchronous                           | $0.30 / $2.50 per MTok | ≈ $198    |

**Caveat added this revision:** the 200-output-token figure assumes a typical
page. A large conglomerate page returning 20+ club entries will need
meaningfully more output tokens than that. This likely won't move the total much
if such pages are a small share of the 180,000, but the actual output token
count from a couple of real conglomerate pages should be checked during
validation rather than trusted from this flat estimate.

This is the ceiling, not the expected number — real volume will likely be lower
once duplicate hits across the 3 queries per school are collapsed, which we
haven't built yet but should before running this at full scale.

## Validation before full run

Before pointing this at all 6,000 schools, run these through the prompt above
and check against known-correct answers:

- \~30 general hard cases: thin/off-domain pages, abbreviation-only identity
  matches (e.g. UConn), known false-positive wrong-school pages
- **A CampusGroups-style page with one shared contact widget across many listed
  clubs** — check that `contact_signal_tier` is correctly graded `"shared"`
  across those rows, not `"direct"` on all of them
- **A small-school page listing several clubs with genuinely distinct inline
  contact info** (no individual club pages at all) — check that this correctly
  produces multiple rows with `"direct"` tier where the page actually supports
  it, so the shared/direct distinction isn't over-corrected into always guessing
  "shared"
- **A page with no real contact info at all, plus a separate page with an
  obfuscated email** ("name at school dot edu") — check that the model reports
  `email_found=false` on the first rather than inventing a plausible address,
  and correctly captures the obfuscated pattern verbatim on the second rather
  than silently normalizing or missing it

This is the cheapest possible check that the combined single-call, single-tier
approach is viable before committing to it at scale — a few cents and a few
minutes.

## Explicitly out of scope for v1

- **Two-tier escalation to a stronger model.** Not building this now. If
  validation shows the single tier missing real cases, this is the natural next
  step — but it adds real complexity (routing logic, a second API integration,
  cascade cost accounting) that isn't justified without evidence it's needed.
- **Separate classify-then-extract calls.** Considered and decided against — see
  "Approach" above. The array-based schema gets classification for free from
  extraction, so splitting would mean paying to comprehend each page twice for
  no benefit.
- **A maintained school-abbreviation/alias table.** Not building this
  proactively — genuinely hard to source completely.
  `school_identifying_terms_found` is a free byproduct that builds toward this
  incidentally over time.
- **Deduplication across the 3 queries per school.** Not built yet; needed
  before the cost estimate above reflects real spend rather than the worst-case
  ceiling.
- **Changes to Tavily query generation.** Out of scope here, though worth a
  later look — if `school_identifying_terms_found` shows a lot of matches are
  abbreviation-based, that's a signal the original search queries (built from
  canonical names) may be missing relevant results too.

## Open risks

1. Whether Gemini 2.5 Flash's world knowledge reliably covers obscure/small
   institutions the way it does well-known ones like UConn — untested, addressed
   by the validation step above.
2. Whether the model reliably separates "shared" from "direct" contact signal on
   conglomerate pages rather than defaulting to one or the other — the main new
   risk introduced by this revision, also addressed by the validation step
   above.
3. Hallucination in the opposite direction: a model asked to find contact info
   can reconstruct a plausible-looking but incorrect address — a wrong domain
   guess, an invented local-part — rather than report what's actually present.
   Mitigated by requiring verbatim-only extraction rather than "find the email"
   framing (see schema notes above); worth spot-checking in validation that
   every reported `contact_signal_snippet` is genuinely present in its source
   page, not synthesized.
