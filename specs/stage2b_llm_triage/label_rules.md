# Triage label rules

**Status:** draft. **Not implemented:** no code applies these rules yet. **Docs
to update when it lands:** none directly. Source of truth for the triage prompt
(`config/triage_prompt.md`), the alias audit and eval labeling. How the step
runs, including the inputs and the keep/drop decision, is in [spec.md](spec.md).

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
2. `tabletop_club`: one organization focused on tabletop RPGs, or on several
   tabletop games (board, card, miniature).
   - These examples qualify, but this is not an exhaustive list:
     - A single-TTRPG club (e.g. D&D only).
     - A general board game club.
     - A club for two or more tabletop games (Magic + Warhammer).
     - "Gaming Club" with no qualifier, with `probable` certainty.
     - A club that may run tabletop, such as an anime-and-gaming society.
     - An event page from a club that is clearly tabletop related.
3. `other`: known to be another type of page. Some examples:
   - A library page, a store, a publisher, a blog or a thesis, even if it is
     about gaming.
   - An article.
   - An event page from an organization that is not a tabletop club (e.g. a
     postdoc association).
   - A social or link page for a club that does not qualify under rule 2, for
     example:
     - A club for a single non-RPG game (chess, Catan, Scrabble, Magic,
       Warhammer, Pokemon TCG).
     - An esports or video game club.
     - A game design or development club, even if it mentions tabletop.
4. `unknown`: not possible to tell.

### institution

Apply in order. The first match wins.

1. `unknown`: the URL or title names both the target and a different
   institution.
   - E.g. A joint event or a page comparing two schools.
2. `not_supported`: the URL or title positively ties the page to someone other
   than the target.
   - The other institution can have phrase in common with the target school such
     as a state, a city, "State", "Community". For example:
     - Central Connecticut State University is not the University of Connecticut
       despite sharing the word "Connecticut".
     - North Seattle College is not South Seattle College.
   - Never assign this label because evidence is missing. It is either:
     - a different school, named in the title or URL or by its domain; or
     - an organization unconnected to any school, for example:
       - a game company (e.g. a Wizards of the Coast page)
       - a store or a public library
       - a fan wiki (e.g. a Fandom page about Magic characters)
       - a personal blog
3. `supported`: the URL or title names the target: its offical name, a common
   alias (e.g. UConn for University of Connecticut), a common acrynom for the
   institution (e.g. BU for Boston University), or an expected shorthand (e.g.
   Northeastern for Northeastern State University). The found phrase must not be
   part of another word (e.g. `mit` inside `summit` does not count for
   Massachusetts Institute of Technology). Some example types of pages that
   would have this label:
   - An article about the target institution.
   - A page describes a campus of the target or the system the target belongs
     to. Some examples:
     - Searching the Gateway campus of CT State: a TTRPG club at its Manchester
       campus.
     - Searching the Manchester campus: a club listing for CT State overall.
4. `unknown`: not possible to tell, including a page that names no one.

### certainty

`page_type_certainty` and `institution_certainty` express doubt about a label.
Label what the result most likely is, and express doubt here rather than by
choosing a different label.

`institution_certainty` is defined as:

- `clear`: the URL is on the institution's official domain, or the URL or page
  name unambiguously names the institution or the institution's alias.
- `probable`: the search page contains an name that could be attributed this
  institution but does meet the criteria for `clear`. E.g. an abbreviation,
  nickname, or acrynym that could refer to another entity.
- `unknown`: value assigned with page_type is `unknown`.

`page_type_certainty` is defined as:

- `clear`:
  - For `tabletop_club`: the page is about a tabletop club which means it needs
    to satisfiy both of the following:
    1. either contains a word associated with clubs (e.g. club, society, guild)
       or it is hosted on a common campus clubs platform (e.g. campusgroups,
       engage, campuslabs, presence, involve)
    2. either contains a word associated with tabletop gaming (e.g. "tabletop",
       "board game", "ttrpg"), references a tabletop roleplay game (like "dnd")
       or references exclusive tabletop roleplay game vocabulary (e.g. "dungeon
       masters", "skill check", "game master").
  - For `conglomerate`: the URL or page name spells out what it is (e.g.
    "student organizations", "clubs and activities", "campus groups") or it has
    directory termions (e.g. "browse organizations", "find a club", "all student
    groups") or it is on a common campus clubs platform (e.g. campusgroups,
    engage, campuslabs, presence, involve).
- `probable`: the page does not meet the criteria for clear but is possibly of
  that classification
  - for `tabletop_club`: it contains words usually associated with tabletop
    gaming (e.g. "adventurers guild", "hit point", "dice", "campaign") or we
    can't can't tell what kind of gaming club it is
  - for `conglomerate`: it contains words usually associated with student
    organizations (e.g. "hub", "student engagement", "student life")
- `unknown`: value assigned with page_type is `unknown`.

## Evidence

Evidence is the substring of the title or URL that drove a label, matched
ignoring case, and empty when nothing matched. `title_evidence_*` quotes the
title and `url_evidence_*` quotes the URL. The code checks on evidence are in
[spec.md](spec.md#model-response).

## Worked examples

Input and expected output pairs are in [examples.jsonl](examples.jsonl).
