# Triage label rules

**Status:** draft

Source of truth for the triage prompt, the alias audit and eval labeling.

## Scope

After rule-based filtering in Stage 2, an LLM model is used to filter results
that are likely irrelevant to finding a TTRPG club.

Earlier filtering already narrows the input:

- Stage 0 (IPEDS dataset build) drops institutions unlikely to have TTRPG
  clubs, such as trade schools.
- Stage 1 (candidate fetch) excludes sites unlikely to host club pages, such as
  news, social media and academic journal sites.
- Stage 2 (pre-llm) runs its rule-based filters. They look for ttrpg and club
  keywords in snippet and remove some shops, events, news and PDFs based on urls.

These rules cover what still gets through.

## Input

For each search result, the model is given:

- the target institution's name and aliases
- the result URL and title
- `domain_relation` which compares the URL's domain with the institution's official
   website.
  - Values are either `on_domain` or `not_on_domain`.
  - About 80% of true club pages are hosted off the university domain (author
    estimate, to be checked in the descriptive pass). While `on_domain` is a
    strong signal for the page being associated with the school, `not_on_domain`
    is not a strong signal for the page NOT being associated with the school.

## Output

### Schema

The output schema is a JSONL file with one row per result.

```json
{ "page_type": "tabletop_club | conglomerate | other | unknown",
  "page_type_certainty": "clear | probable",
  "title_evidence_for_page_type": "[substring]", 
  "url_evidence_for_page_type": "[substring]",
  "institution": "supported | not_supported | unknown",
  "institution_certainty": "clear | probable",
  "title_evidence_for_institution": "[substring]", 
  "url_evidence_for_institution": "[substring]"}
```

`page_type` and `institution` are independent. A tabletop club page for the
wrong school is `tabletop_club` + `not_supported`.

### page_type

Apply in order. The first match wins.

1. `conglomerate`: lists many student organizations (directory, category
   listing or vendor search page), regardless of topic.
2. `tabletop_club`: one organization focused on tabletop RPGs, or on several
   tabletop games (board, card, miniature). A single-TTRPG club (D&D only)
   qualifies. A club for a single non-RPG game does not.
3. `other`: everything else, such as a library page, a blog, a store, etc.
4. `unknown`: not possible to tell.

### institution

- `supported`: match the target's name or an alias in the URL or title
- `not_supported`: the URL or title names a different institution or clearly
  unaffiliated with any institution
- `unknown`: not possible to tell

### evidence

`*_evidence_for_*` is the URL or title substring that drove `page_type` or `institution`
in the input as sent, ignoring case. It is empty when nothing matched.

## Downstream use

Code drops a result when `page_type` is `other` or when `institution` is `not_supported`.
Every other result goes to Stage 3 including `unknown`. These are both tunable on
`*_certainty` and `*_evidence_for_*` fields in code.

A false drop loses a club page permanently. A false keep costs one render.
Therefore:

- Label what the result most likely is, and express doubt through
  `type_certainty`.
- Assign `not_supported` only on positive evidence of a different school, another
  organization (e.g. library page, a store, company), there is no organization
  (e.g. personal blog page, wiki), never on missing evidence.

## Example Classifications

### Page type cases

| Case | page_type | Note |
| --- | --- | --- |
| "Gaming Club", no qualifier | `tabletop_club` | deliberate hedge toward keep |
| General board game club | `tabletop_club` | |
| Two or more tabletop games (Magic + Warhammer) | `tabletop_club` | |
| Anime-and-gaming society | `tabletop_club` | they may run tabletop |
| Social or link page for one club | `tabletop_club` or `other` by the club's focus | |
| "Recreation & Gaming" category page | `conglomerate` | |
| "Campus clubs" or "Student organizations" page | `conglomerate` | |
| Esports or video game club | `other` | |
| Game design or development club | `other` | even if it mentions tabletop |
| Single-game club (chess, Catan, Scrabble, Magic, Warhammer, Pokemon TCG) | `other` | |
| Event page for a club meeting | `other` | the event is often a one-off and the club is not a ttrpg club |
| Thesis, blog, store or publisher about gaming | `other` | topic keywords alone never make a club |
| An article | `other` | |

### Institution cases

| Case | institution | Note |
| --- | --- | --- |
| TTRPG club for a campus of the same institution (e.g. ttrpg club for the Manchester campus of CT State when we're searching for Gateway campus) | `supported` | clubs are deduplicated later, this is harmless to keep |
| TTRPG club for the overall institution when searching a campus of the institution (e.g. club listing for CT Stat when we're searching for Manchester campus) | `supported` | clubs are deduplicated later, this is harmless to keep |
| Community group with no student affiliation (game store, library) | `not_supported` | |
| An article | `not_supported` | |

## Full Examples

Some examples encoutered during manual inspection, illustrative but not comprehensive:

**Champlain College**

```json
input {
  "university": "Champlain College",
  "aliases": [],
  "url": "https://www.champlain.edu/clubs-activities-affinity-groups/tabletop-games-club",
  "title": "Tabletop Games Club | Champlain College, Burlington, VT",
  "domain_relation": "on_domain"
}
output {
  "page_type": "tabletop_club",
  "page_type_certainty": "clear",
  "title_evidence_for_page_type": "tabletop games club",
  "url_evidence_for_page_type": "tabletop-games-club",
  "institution": "supported",
  "institution_certainty": "clear",
  "title_evidence_for_institution": "Champlain College",
  "url_evidence_for_institution": "champlain.edu"
}
```

**Northwest State Community College**

```json
input {
  "university": "Northwest State Community College",
  "aliases": [],
  "url": "https://northweststate.edu/student-organizations",
  "title": "Student Organizations - Northwest State Community College",
  "domain_relation": "on_domain"
}
output {
  "page_type": "conglomerate",
  "page_type_certainty": "clear",
  "title_evidence_for_page_type": "student organizations",
  "url_evidence_for_page_type": "student-organizations",
  "institution": "supported",
  "institution_certainty": "clear",
  "title_evidence_for_institution": "Northwest State Community College",
  "url_evidence_for_institution": "northweststate.edu"
}
```

**Massachusetts Institute of Technology**

```json
input {
  "university": "Massachusetts Institute of Technology",
  "aliases": ["mit"],
  "url": "https://assassin.mit.edu",
  "title": "MIT Assassins' Guild",
  "domain_relation": "on_domain"
}
output {
  "page_type": "tabletop_club",
  "page_type_certainty": "probable",
  "title_evidence_for_page_type": "assassins' guild",
  "url_evidence_for_page_type": "",
  "institution": "supported",
  "institution_certainty": "clear",
  "title_evidence_for_institution": "mit",
  "url_evidence_for_institution": "mit.edu"
}
```

**University of Connecticut**

```json
input {
  "university": "University of Connecticut",
  "aliases": [],
  "url": "https://visitour.io/central-connecticut-state-university/social-based-club-tabletop-games-club",
  "title": "Tabletop Games Club (Central Connecticut State University's Social-based Clubs)",
  "domain_relation": "not_on_domain"
}
output {
  "page_type": "tabletop_club",
  "page_type_certainty": "clear",
  "title_evidence_for_page_type": "tabletop games club",
  "url_evidence_for_page_type": "tabletop-games-club",
  "institution": "not_supported",
  "institution_certainty": "clear",
  "title_evidence_for_institution": "Central Connecticut State University",
  "url_evidence_for_institution": "central-connecticut-state-university"
}
```

**Tufts University**

```json
input {
  "university": "Tufts University",
  "aliases": [],
  "url": "https://now.tufts.edu/2024/02/14/pieces-fall-place-fletchers-mahjong-club",
  "title": "Pieces Fall into Place for Fletcher’s Mahjong Club | Tufts Now",
  "domain_relation": "on_domain"
}
output {
  "page_type": "other",
  "page_type_certainty": "clear",
  "title_evidence_for_page_type": "mahjong club",
  "url_evidence_for_page_type": "mahjong-club",
  "institution": "not_supported",
  "institution_certainty": "probable",
  "title_evidence_for_institution": "Tufts University"
  "url_evidence_for_institution": "tufts.edu"
}
```

### Gotchas

Hand-built gotchas encountered during manual inspection, not comprehensive:

- `summit.campusgroups.com` returned for an MIT query: though it contains the
  substring "MIT", it is not a whole token, so not `supported`.
