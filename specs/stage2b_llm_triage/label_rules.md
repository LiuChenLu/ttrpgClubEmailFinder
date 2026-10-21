# Triage label rules

**Status:** draft. **Not implemented:** no code applies these rules yet. **Docs
to update when it lands:** none directly. Source of truth for the triage prompt
(`config/triage_prompt.md`), the alias audit and eval labeling. How the step
runs, including the inputs and the keep/drop decision, is in
[spec.md](spec.md).

## Input

The fields the model receives and how they are computed are in
[spec.md](spec.md#preprocessing).

`domain_relation` of `on_domain` is a strong signal that the page is associated
with the school. `not_on_domain` is not a strong signal that it is NOT, because
most true club pages are hosted off the university domain.

## Output

The output fields and their enum values are defined in
[schema.json](schema.json). The model returns one object per result.

`page_type` and `institution` are independent. A tabletop club page for the
wrong school is `tabletop_club` + `not_supported`.

### page_type

Apply in order. The first match wins.

1. `conglomerate`: lists many student organizations (directory, category listing
   or vendor search page), regardless of topic.
   - A "Campus clubs" or "Student organizations" page.
   - A topic category page such as "Recreation & Gaming".
2. `tabletop_club`: one organization focused on tabletop RPGs, or on several
   tabletop games (board, card, miniature).
   - Qualifies:
     - A single-TTRPG club (D&D only).
     - A general board game club.
     - A club for two or more tabletop games (Magic + Warhammer).
     - "Gaming Club" with no qualifier, with `probable` certainty. A
       deliberate lean toward keeping (see
       [spec.md](spec.md#design-priority-recall)).
     - An anime-and-gaming society. They may run tabletop.
     - A social or link page for one club, when that club qualifies.
     - An event page from a club that is clearly tabletop related.
   - Does not qualify (falls through to `other`):
     - A club for a single non-RPG game (chess, Catan, Scrabble, Magic,
       Warhammer, Pokemon TCG).
     - An esports or video game club.
     - A game design or development club, even if it mentions tabletop.
3. `other`: known to be another type of page. Topic keywords alone never make a
   club.
   - A library page, a store, a publisher, a blog or a thesis, even if it is
     about gaming.
   - An article.
   - An event page from an organization that is not a tabletop club (e.g. a
     postdoc association).
   - A social or link page for a club that does not qualify under rule 2.
4. `unknown`: not possible to tell.

### institution

Compare whole institution names:

- A word the result shares with the target's name (a state, a city, "State",
  "Community") does not make it the target.
  - Central Connecticut State University is not the University of Connecticut
    despite sharing the word "Connecticut".
  - North Seattle College is not South Seattle College.
- A campus of the target, or the system the target belongs to, is the target,
  not a different institution.
  - Searching the Gateway campus of CT State: a TTRPG club at its Manchester
    campus.
  - Searching the Manchester campus: a club listing for CT State overall.

Apply in order. The first match wins.

1. `unknown`: the URL or title names both the target and a different
   institution.
   - A joint event, or a page comparing two schools.
2. `not_supported`: the URL or title positively ties the page to someone other
   than the target. Never assign it because evidence is missing. It is either:
   - a different school, named in the title or URL or by its domain; or
   - an organization unconnected to any school, when the URL and title do not
     name the target:
     - a game company (a Wizards of the Coast page)
     - a store or a public library
     - a fan wiki (a Fandom page about Magic characters)
     - a personal blog
3. `supported`: the URL or title names the target: its name, an alias, a common
   nickname (UConn), a distinctive part of its name as a whole word (`mit`
   inside `summit` does not count), or its domain.
   - An article about the target institution.
4. `unknown`: not possible to tell, including a page that names no one.

### certainty

`page_type_certainty` and `institution_certainty` express doubt about a label.
Label what the result most likely is, and express doubt here rather than by
choosing a different label.

- `clear`: the URL and title settle the label, and a second labeler would not
  choose differently.
- `probable`: the label is the most likely reading, but the URL and title leave
  room for another. Example: ["Gaming Club"](#page_type) with no qualifier.

## Evidence

Evidence is the substring of the title or URL that drove a label, matched
ignoring case, and empty when nothing matched. `title_evidence_*` quotes the
title and `url_evidence_*` quotes the URL. The code checks on evidence are in
[spec.md](spec.md#model-response).

## Worked examples

Input and expected output pairs are in [examples.jsonl](examples.jsonl).
