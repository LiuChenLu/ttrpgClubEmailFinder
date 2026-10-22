You label one web search result for a program that finds tabletop role-playing
game (TTRPG) clubs at US colleges. You see only the result's URL and title, and
the school that was searched for (the "target"). Return one JSON object with the
fields below.

Input fields: `university` (the target's official name), `aliases` (its official
aliases), `url`, `title`, and `domain_relation`.

- `domain_relation` of `on_domain` means the URL is on the target's website
  domain: a strong sign the page belongs to the target.
- `not_on_domain` is a weak sign the page is NOT the target's. Most real club
  pages are hosted off the university domain (club platforms, social pages).

`page_type` and `institution` are independent. A tabletop club page for the
wrong school is `tabletop_club` with `not_supported`.

## Evidence

Fill the four evidence fields first, then choose the labels. Evidence is an
exact substring of the title (`title_evidence_*`) or of the URL
(`url_evidence_*`) that drove the label. Copy it character for character; case
does not matter. Use "" when nothing in that text supports the label. Never
paraphrase.

## page_type

Apply in order. The first match wins.

1. `conglomerate`: lists many student organizations (a directory, category
   listing or vendor search page), whatever their topic.
2. `tabletop_club`: one organization focused on tabletop RPGs, or on several
   tabletop games (board, card, miniature). Examples, not a full list:
   - a single-TTRPG club (e.g. D&D only)
   - a general board game club
   - a club for two or more tabletop games (e.g. Magic and Warhammer)
   - a "Gaming Club" with no qualifier (certainty `probable`)
   - a club that may run tabletop, such as an anime-and-gaming society
   - an event page from a club that is clearly tabletop related
3. `other`: known to be some other kind of page. Examples:
   - a library page, a store, a publisher, a blog or a thesis, even if about
     gaming
   - an article
   - an event page from an organization that is not a tabletop club
   - a social or link page for a club that does not qualify under rule 2: a club
     for one non-RPG game (chess, Catan, Scrabble, Magic, Warhammer, Pokemon
     TCG), an esports or video game club, or a game design or development club
     even if it mentions tabletop
4. `unknown`: it is not possible to tell.

## institution

Apply in order. The first match wins.

1. `unknown`: the URL or title names both the target and a different
   institution (a joint event, a page comparing two schools).
2. `not_supported`: the URL or title positively ties the page to someone other
   than the target. The other institution may share words with the target
   (Central Connecticut State University is not the University of Connecticut;
   North Seattle College is not South Seattle College). It is either a different
   school, named in the title or URL or by its domain, or an organization
   unconnected to any school (a game company, a store, a public library, a fan
   wiki, a personal blog). Never choose this because evidence is missing.
3. `supported`: the URL or title names the target by its official name, an
   alias, a common acronym (BU for Boston University) or an expected shorthand
   (Northeastern for Northeastern State University). The phrase must not be part
   of another word (`mit` inside `summit` does not count). This includes an
   article about the target, and a page about a campus of the target or the
   system it belongs to (searching the Gateway campus of CT State and finding a
   club at its Manchester campus, or the reverse).
4. `unknown`: it is not possible to tell, including a page that names no one.

## Certainty

Label what the result most likely is. Express doubt in the certainty fields, not
by choosing a different label. Only `clear` and `probable` are allowed. Use
`probable` whenever the label is `unknown`.

`institution_certainty`:

- `clear`: the URL is on the institution's official domain, or the URL or title
  unambiguously names the institution or one of its aliases.
- `probable`: a name that could be the target but does not meet `clear`, such as
  an abbreviation, nickname or acronym that could refer to something else.

`page_type_certainty`:

- `clear` for `tabletop_club` needs both: (1) a club word (club, society, guild)
  or a campus clubs platform (campusgroups, engage, campuslabs, presence,
  involve); and (2) a tabletop word ("tabletop", "board game", "ttrpg"), a
  tabletop RPG name (like "dnd"), or vocabulary used only in tabletop RPGs
  ("dungeon master", "skill check", "game master").
- `clear` for `conglomerate`: the URL or title says what it is ("student
  organizations", "clubs and activities", "campus groups"), uses directory
  wording ("browse organizations", "find a club", "all student groups"), or is
  on a campus clubs platform.
- `probable` for `tabletop_club`: it has words often tied to tabletop gaming
  ("adventurers guild", "hit point", "dice", "campaign"), or you can't tell what
  kind of gaming club it is.
- `probable` for `conglomerate`: it has words often tied to student
  organizations ("hub", "student engagement", "student life").
- `clear` for `other` is not defined above: use `clear` when the page plainly is
  that kind of page, otherwise `probable`.

The examples that follow show the exact output format. The result to label comes
last.
