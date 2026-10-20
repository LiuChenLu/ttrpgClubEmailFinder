# Triage label rules

**Status:** draft. **Not implemented:** no code applies these rules yet. **Docs
to update when it lands:** none directly. These rules feed the triage prompt
(`config/triage_prompt.md`), the alias audit and eval labeling. See
[spec.md](spec.md).

Source of truth for the triage prompt, the alias audit and eval labeling.

## Scope

After rule-based filtering in Stage 2, an LLM model would be used to filter
results that are likely irrelevant to finding a TTRPG club.

Earlier stages already narrow the input and are documented in
[`docs/stages/`](../../docs/stages/stage2_filter_candidates.md) (stages 0 to 2).
These rules cover what still gets through. How this step would run is in
[spec.md](spec.md).

## Input

For each search result, the model is given:

- the target institution's name and aliases
- the result URL and title
- `domain_relation`: `on_domain` if the result is hosted on the institution's
  own domain, otherwise `not_on_domain`. How it is computed: [spec.md](spec.md).

`on_domain` is a strong signal that the page is associated with the school.
`not_on_domain` is not a strong signal that it is NOT, because most true club
pages are hosted off the university domain.

## Output

The output fields and their enum values are defined in
[schema.json](schema.json). The model returns one object per result.

`page_type` and `institution` are independent. A tabletop club page for the
wrong school is `tabletop_club` + `not_supported`.

### page_type

Apply in order. The first match wins.

1. `conglomerate`: lists many student organizations (directory, category listing
   or vendor search page), regardless of topic.
2. `tabletop_club`: one organization focused on tabletop RPGs, or on several
   tabletop games (board, card, miniature). A single-TTRPG club (D&D only)
   qualifies. A club for a single non-RPG game does not.
3. `other`: known to be another type of page, such as a library page, a blog, a
   store, etc.
4. `unknown`: not possible to tell.

### institution

Compare whole institution names. A word the result shares with the target's name
(a state, a city, "State", "Community") is not sufficient support when the
result names a different institution. For example, Central Connecticut State
University is not the University of Connecticut despite sharing the word
"Connecticut".

Apply in order. The first match wins.

1. `unknown`: the URL or title names both the target and a different institution
   (e.g. a joint event or a page comparing two schools).
2. `not_supported`: the URL or title names a different institution, or is
   clearly not tied to any institution (a store, a library, a personal blog).
3. `supported`: the URL or title names the target: its name, an alias, a common
   nickname (UConn), a distinctive part of its name as a whole word (`mit`
   inside `summit` does not count), or its domain.
4. `unknown`: not possible to tell.

A campus of the target, or the system the target belongs to, is the target, not
a different institution (see the case table below).

### certainty

`page_type_certainty` and `institution_certainty` express doubt about a label.

- `clear`: the URL and title settle the label, and a second labeler would not
  choose differently.
- `probable`: the label is the most likely reading, but the URL and title leave
  room for another (e.g. a club name that doesn't say what the club plays).

## Example Classifications

### Page type cases

| Case                                                                     | page_type                                      | Note                                                          |
| ------------------------------------------------------------------------ | ---------------------------------------------- | ------------------------------------------------------------- |
| "Gaming Club", no qualifier                                              | `tabletop_club`                                | deliberate hedge toward keep                                  |
| General board game club                                                  | `tabletop_club`                                |                                                               |
| Two or more tabletop games (Magic + Warhammer)                           | `tabletop_club`                                |                                                               |
| Anime-and-gaming society                                                 | `tabletop_club`                                | they may run tabletop                                         |
| Social or link page for one club                                         | `tabletop_club` or `other` by the club's focus |                                                               |
| "Recreation & Gaming" category page                                      | `conglomerate`                                 |                                                               |
| "Campus clubs" or "Student organizations" page                           | `conglomerate`                                 |                                                               |
| Esports or video game club                                               | `other`                                        |                                                               |
| Game design or development club                                          | `other`                                        | even if it mentions tabletop                                  |
| Single-game club (chess, Catan, Scrabble, Magic, Warhammer, Pokemon TCG) | `other`                                        |                                                               |
| Event page for a club meeting                                            | `other`                                        | the event is often a one-off and the club is not a ttrpg club |
| Thesis, blog, store or publisher about gaming                            | `other`                                        | topic keywords alone never make a club                        |
| An article                                                               | `other`                                        |                                                               |

### Institution cases

| Case                                                                                                                                                          | institution     | Note                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- | ------------------------------------------------------ |
| TTRPG club for a campus of the same institution (e.g. ttrpg club for the Manchester campus of CT State when we're searching for Gateway campus)               | `supported`     | clubs are deduplicated later, this is harmless to keep |
| TTRPG club for the overall institution when searching a campus of the institution (e.g. club listing for CT State when we're searching for Manchester campus) | `supported`     | clubs are deduplicated later, this is harmless to keep |
| Different school sharing a word with the target (searching South Seattle College, result is North Seattle College)                                            | `not_supported` | shared words don't count                               |
| Result names both the target and a different school                                                                                                           | `unknown`       | real doubt; kept                                       |
| Community group with no student affiliation (game store, library)                                                                                             | `not_supported` |                                                        |
| An article                                                                                                                                                    | `not_supported` |                                                        |

## Worked examples

Input and expected output pairs are in [examples.jsonl](examples.jsonl).
