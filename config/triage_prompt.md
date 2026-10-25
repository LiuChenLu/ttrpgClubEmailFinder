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

Write each evidence pair just before the label it supports. Evidence is an exact
substring of the title (`title_evidence_*`) or of the URL (`url_evidence_*`)
that drove the label. Copy it character for character; case does not matter. Use
"" when nothing in that text supports the label. Never paraphrase. Evidence must
support the label you chose, and topic words that point toward a different label
aren't evidence.

For page type `other`, evidence is a phrase that identifies the page as
something other than a club or collection of clubs. Many other pages have no
clear substring: in that case, "" is appropriate even if the certainty is
`clear`.

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
   - a page whose name evokes tabletop RPG culture without saying so (e.g. 'The
     Guild', 'Dungeons and Biology', 'Adventurers'). This does not apply to an
     established non-gaming name (e.g. Screen Actors Guild) or a guild or club
     word qualified by a non-gaming trade or hobby (e.g. Glee Club, Teachers
     Guild). Certainty `probable`. Nothing needs to say 'club'.
3. `other`: known to be something else, title or url identifies the page as an
   article, blog, news, library, store, an event run by a non-tabletop group,
   etc. Evocative wording alone never makes a page `other`. Examples:
   - a library page, a store, a publisher, a blog or a thesis, even if about
     gaming
   - an article
   - an event page from an organization that is not a tabletop club
   - a social or link page for a club that does not qualify under rule 2: a club
     for one non-RPG game (chess, mahjong, Scrabble, Magic, Warhammer, Pokemon
     TCG), an esports or video game club, or a game design or development club
     even if it mentions tabletop
4. `unknown`: it is not possible to tell.

## institution

Apply in order. The first match wins.

1. `not_supported`: the URL or title names both the target and a different
   institution (e.g. a joint event, a page comparing two schools). A campus of
   the target or a sister school in its system does not count.
2. `not_supported`: the URL or title positively ties the page to someone other
   than the target. The other institution may share words with the target (e.g.
   Central Connecticut State University is not the University of Connecticut;
   North Seattle College is not South Seattle College). It is either a different
   school, named in the title or URL or by its domain, or an organization
   unconnected to any school (e.g. a game company, a store, a public library, a
   fan wiki, a personal blog). A campus of the target or a sister school in its
   system does not count. Never choose this because evidence is missing.
3. `supported`: the URL or title names the target by its official name, an
   alias, a common acronym (BU for Boston University) or an expected shorthand
   (Northeastern for Northeastern State University). The phrase must not be part
   of another word (e.g. `mit` inside `summit` does not count). This includes an
   article about the target, and a page about a campus of the target, the system
   it belongs to, or a sister school in the same system.
4. `unknown`: it is not possible to tell, including a page that names no one.

## Certainty

Label what the result most likely is. Express doubt in the certainty fields, not
by choosing a different label. Only `clear` and `probable` are allowed. Use
`probable` whenever the label is `unknown`.

`institution_certainty`:

- `clear` for `supported`: the URL is on the institution's official domain, or
  the URL or title unambiguously names the institution or one of its aliases.
- `clear` for `not_supported`: another institution or organization is
  unambiguous, or there is clearly no institution.
- `probable` for `supported`: a name that could be the target but does not meet
  `clear`, such as an abbreviation, nickname or acronym that could refer to
  something else.
- `probable` for `not_supported`: another institution name that is ambiguous or
  shares words with the target.

- `clear` for `tabletop_club` needs both: (1) a group of people noun (e.g.
  "gamers", "adventurers"), a club word (club, society, guild) or is on a campus
  clubs platform (campusgroups, engage, campuslabs, presence, involve); and (2)
  a tabletop word ("tabletop", "board game", "ttrpg"), a tabletop RPG name (like
  "dnd"), or vocabulary used only in tabletop RPGs ("dungeon master", "skill
  check", "game master").
- `clear` for `conglomerate`: the URL or title says what it is ("student
  organizations", "clubs and activities", "campus groups"), uses directory
  wording ("browse organizations", "find a club", "all student groups"), or is
  on a campus clubs platform.
- `probable` for `tabletop_club`: any of: (1) it suggest group of people and has
  words often tied to tabletop gaming ("adventurers guild", "hit point", "dice",
  "campaign"); (2) you can't tell what kind of gaming club it is; or (3) the
  name only evokes tabletop RPG culture (the last bullet of rule 2).
- `probable` for `conglomerate`: it has words often tied to student
  organizations ("hub", "student engagement", "student life").
- `clear` for `other`: the page is not that kind of page.

The examples that follow show the exact output format. The result to label comes
last.
