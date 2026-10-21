# LLM Page-Classifier Eval: Dataset Documentation

**Status:** generated, not trusted. This file and `eval.csv` do not match
[label_rules.md](../label_rules.md) (label names, definitions and file names
differ). Do not use either as ground truth or as a source for what a label
means; use [label_rules.md](../label_rules.md). They will be rewritten to match
later.

_Companion to `llm_page_classifier_eval.csv` · 49 rows · written 2026-10-15 for
the TTRPG club finder pipeline_

## 1. Purpose

The pipeline searches for US college tabletop-RPG and gaming club pages and
collects contact info. Stage 1 returns many search results per institution, and
most of them are not club pages. This eval tests a lightweight LLM that sees
only three strings per search result (the institution's official name, the page
title and the page URL) and returns two labels:

- `type`: what kind of page it is. One of `conglomerate` (a page listing many
  different clubs), `single_club` (a page for one club), `other`, or `not_sure`.
- `might_match_institution`: `yes` or `no`, whether the page could belong to
  that institution.

The design priority is recall. When unsure, the model should keep a page
(`single_club`, `conglomerate` or `not_sure`) rather than discard it (`other`),
and should answer `yes` on institution match unless the title or URL gives
positive evidence of a different school. A wrongly discarded club is a lost
lead; a wrongly kept junk page costs only one extra downstream fetch.

This is a coverage set, not a random sample. Each kind of page seen in real
search results appears at least once, so rare cases are over-represented (53% of
rows are keep-worthy, versus a small fraction in real Stage 1 output). Use it to
regression-test prompt changes, not to estimate production accuracy.

## 2. File format

- File: `llm_page_classifier_eval.csv`. UTF-8 without a BOM, header row,
  standard CSV quoting (titles containing commas or quotes are quoted). Load
  with `csv.DictReader(open(path, newline='', encoding='utf-8'))` or pandas.
- 49 rows, one row per (institution, page) pair. Every field is non-empty.
- Rows are grouped by expected type and are not shuffled. The `id` prefix
  encodes the expected type: `C` = conglomerate, `S` = single_club, `N` =
  not_sure, `O` = other. Shuffle before sending several rows in one batch.

Columns, in order:

- `id`: unique row ID such as `S02`.
- `institution`: the institution name as the model would receive it. Model
  input. Naming style is mixed (for example `Indiana University-South Bend` and
  `University of Massachusetts Amherst`) and was not checked against the
  pipeline's `institutions.csv`.
- `title`: the page title. Model input. Some are generic or slug-like on purpose
  (`club signup`, `All Club Events`, `Roll For Initiative`). Titles found by web
  search may lack the ` | Site Name` suffix that Tavily would return.
- `url`: the full page URL. Model input. Copy it exactly; odd details are real
  (the Scribd URL ends in `Studiese`).
- `institution_domain`: OPTIONAL extra input. The institution's own primary
  domain, such as `uconn.edu` or `lccc.wy.edu`, given in the style of IPEDS
  WEBADDR. Not part of the base spec; provide it only in an A/B variant of the
  prompt.
- `expected_type`: ground-truth page type (Section 3.1).
- `expected_might_match_institution`: ground-truth institution label: `yes`,
  `no` or `any` (Section 3.2).
- `case`: scenario tag with 20 distinct values (Section 5.2).
- `confidence`: `clear` (a careful labeler would agree from title and URL) or
  `judgment` (reasonable people could differ; 17 rows).
- `origin`: provenance (Section 5.3).
- `notes`: one or two sentences of labeling rationale.

Never show `expected_type`, `expected_might_match_institution`, `case`,
`confidence`, `origin`, `notes` or `id` to the model under test. `case` and
`notes` in particular give away the answer.

## 3. Label definitions

### 3.1 expected_type

- `conglomerate`: the page's purpose is to list many different student clubs or
  organizations. Includes an A-Z directory, an org-portal listing, a college- or
  department-level list of clubs, and an academic-catalog page that lists clubs.
- `single_club`: the page's subject is one specific student club that is
  tabletop-RPG, tabletop or gaming related. Includes the club's own page,
  profile or sign-up page on a school site, on a vendor platform
  (CampusLabs/Engage, CampusGroups, involvement-platform subdomains) or on the
  club's own site. Page type is judged independently of the institution: a UMass
  club page paired with MIT is still `single_club`.
- `not_sure`: title and URL alone cannot show whether the page is a club page, a
  directory, an event listing or an article, but it could plausibly be a lead
  for a TTRPG club. Includes event listings for TTRPG clubs and pages with
  TTRPG-flavored but uninformative titles. This label reflects what is
  determinable from title and URL, not what the page truly contains.
- `other`: clearly not a club page or directory. Includes news or feature
  articles (even ones about a TTRPG club), blogs, forum threads, stores and
  cafes, indie games, campus facilities, generic campus or admissions pages,
  event schedules, documents and PDFs, SEO spam, athletics pages, and pages or
  events for non-TTRPG clubs such as chess or anime.

### 3.2 expected_might_match_institution

- `yes`: no positive evidence in the title or URL of a different institution or
  campus. Covers a host on the institution's own domain; a vendor host whose
  subdomain or title names the institution (for example
  `umassamherst.campuslabs.com` for UMass Amherst); a domain shared across a
  multi-campus system (`rutgers.edu` is acceptable for any Rutgers campus); and
  a third-party page with nothing contradicting it.
- `no`: positive evidence that the page belongs to a different institution or
  campus. The title or subdomain names another school, the host is another
  school's domain (including a sibling campus with its own domain, such as
  `iusb.edu` on an Indiana University-Bloomington row), or the host is a K-12
  district.
- `any`: not scored (9 rows, all with expected_type `other`). Used when the page
  is tied to no institution (forum, store, game, document, spam, schedule) or is
  about the institution but not by it (a third-party magazine article). Either
  model answer is acceptable.
- The model under test only ever outputs `yes` or `no`.
- One deliberate exception to the evidence rule: row S10 is a real page from
  Concordia University Texas paired with Concordia University Irvine. Nothing in
  the name, title or URL separates them, so it is labeled `yes` under the
  err-toward-match rule even though the truth is a different school. If the
  model is given `institution_domain` (`cui.edu`), the correct answer becomes
  `no`.

### 3.3 Edge-case conventions

- Non-TTRPG club pages (Chess, Anime) are `other`. This is a spec decision: if
  `single_club` should mean any club, flip rows O10, O11 and O12 and judge topic
  downstream.
- An article about a club (student newspaper, school-site feature, admissions
  story) is `other`, even for a TTRPG club. An article that profiles many clubs
  (O07) is `other`, not `conglomerate`.
- An event listing for a TTRPG club is `not_sure`. An event listing for a
  non-TTRPG club is `other`.
- Labels follow title and URL, not hidden page content. N03's real page is a
  news feature, but nothing in its title or URL shows that, so it is `not_sure`.
- Multi-campus systems: a shared system domain is `yes` for any campus; a
  different campus's own domain is `no`.
- A page on the institution's own domain is `yes` on the institution field
  regardless of type, including for `other` pages.
- O14 is a `.pdf` URL. Stage 2 already drops `.pdf` URLs, so it never reaches
  the LLM in the current pipeline; it is kept as a robustness check.

## 4. Scoring guidance

Plain accuracy is the wrong headline because errors are not equally costly.
Report:

- Lead recall: among the 26 rows whose expected_type is not `other`, the
  fraction the model does not label `other`. The target is 100%; each miss is a
  lost club. For `not_sure` rows any non-`other` answer passes, and an exact
  match requires `not_sure`.
- Discard rate: among the 23 `other` rows, the fraction labeled `other`. Misses
  here are wasted downstream work, a soft error.
- Strict type accuracy and a confusion matrix, as diagnostics.
- Institution: skip `any` rows, leaving 40 scored rows (31 `yes`, 9 `no`).
  Report the false-`no` rate on `yes` rows (costly: drops a real club)
  separately from the false-`yes` rate on `no` rows (cheap: caught later). An
  always-`yes` model scores 77.5% on these rows, so look at recall on the `no`
  rows.
- Slice results by `case` and by `confidence`. Treat `clear` rows as the gate
  and `judgment` rows as diagnostics.
- With 26 keep-worthy rows, one miss moves lead recall by about 3.8 points.

## 5. Coverage

### 5.1 Expected type by institution label (row counts)

- `single_club` (12): 9 yes, 3 no
- `conglomerate` (10): 7 yes, 3 no
- `not_sure` (4): 3 yes, 1 no
- `other` (23): 12 yes, 2 no, 9 any
- Totals: 49 rows; 26 keep-worthy (any type except `other`) and 23 `other`;
  institution labels 31 yes, 9 no, 9 any.

### 5.2 Cases and counts

Each bullet gives the `case` tag, the number of rows, the row IDs, and the
labels those rows carry.

Directories (expected_type `conglomerate`):

- `directory` (7; C01, C03, C04, C06, C07, C08, C09): yes. On-domain,
  vendor-hosted, college-level and catalog-hosted club lists.
- `directory_wrong_school` (3; C02, C05, C10): no. A real directory paired with
  a lookalike or sibling institution.

Single TTRPG or gaming clubs (expected_type `single_club`):

- `ttrpg_club_page` (8; S01, S03, S04, S05, S06, S07, S09, S12): yes. Varied
  hosting: school CMS, student-government subsite, department site, vendor
  platforms, opaque `?p=` URLs, generic titles.
- `ttrpg_club_page_wrong_school` (3; S02, S08, S11): no. Includes a sibling-name
  school, a lookalike domain and a K-12 district page.
- `wrong_school_undetectable` (1; S10): yes by rule, though the truth is a
  different school.

Keep-worthy but ambiguous (expected_type `not_sure`):

- `ttrpg_club_event_page` (3; N01 yes, N02 no, N04 yes): event listings that
  name a TTRPG club.
- `ambiguous` (1; N03): yes. TTRPG-flavored title, opaque URL.

Discard (expected_type `other`):

- `campus_other_page` (2; O01, O02): yes. Campus and admissions pages.
- `campus_facility` (1; O03): yes. A student-union game room.
- `news_article` (6; O04, O05, O06, O07, O08 yes; O16 any): student-newspaper
  articles, school-site feature stories, an article profiling many clubs, a
  third-party magazine piece.
- `blog` (2; O09 yes, O23 any): a course blog post and a student-run blog on a
  free host.
- `non_ttrpg_club_page` (2; O10, O12): yes. Chess and Anime club pages.
- `non_ttrpg_club_event` (1; O11): yes. An Anime Club calendar event.
- `wrong_school_other` (2; O13, O14): no. Athletics pages for a different
  university.
- `forum_or_community` (2; O15, O19): any.
- `event_schedule` (1; O17): any. A convention schedule.
- `document` (1; O18): any. A document-hosting page.
- `indie_game` (1; O20): any. A one-page TTRPG on itch.io.
- `store_or_cafe` (1; O21): any. A game-cafe listing on a tourism site.
- `spam_seo` (1; O22): any. A content-farm page whose title names the school.

The case list covers: directory pages, one-off events by non-TTRPG clubs,
non-TTRPG club pages, news articles, indie games, wrong-school pages, stores and
shops, blogs, and campus facilities, plus forums, event schedules, documents,
SEO spam, generic campus pages and event listings for TTRPG clubs.

### 5.3 Provenance and confidence

`origin` values:

- `user_pipeline` (10; C03, O01, O02, O13 to O19): copied verbatim from real
  Stage 1 output supplied by the maintainer.
- `user_spec` (4; C01, S01, S02, S03): examples from the maintainer's spec.
  Titles are as the maintainer wrote them; the pages are JS-rendered and were
  not independently verified.
- `web_search` (28): real pages found by web search on 2026-10-15, each paired
  with its true owner.
- `constructed_pairing` (7; C02, C05, C10, S08, S10, S11, N02): a real page
  paired with a different real institution to create a wrong-school or lookalike
  case. Both halves are real; only the pairing is synthetic.

`confidence` values: `clear` (32 rows) and `judgment` (17 rows: C05, C10, S08,
S10, S12, N01, N02, N03, N04, O06, O07, O08, O10, O11, O12, O14, O23). Review
the `judgment` rows first.

### 5.4 Minimal pairs

Six pages appear twice with the same title and URL but a different institution,
so only the institution label differs. They show whether the model reads the
institution or only the page. Keep both rows of a pair in the same dev or test
split.

- C01 and C02: UMass organizations directory; UMass Amherst vs Amherst College.
- C04 and C05: Indiana University South Bend student-org list; South Bend vs
  Bloomington.
- C09 and C10: a `miamioh.edu` club list; Miami University-Oxford vs University
  of Miami.
- S02 and S03: UMass tabletop club page; MIT vs UMass Amherst.
- S07 and S08: a `colum.edu` D&D page; Columbia College Chicago vs Columbia
  University in the City of New York.
- N01 and N02: a UMass library event page; UMass Amherst vs Amherst College.

## 6. Working with the file

1. Load the rows with `csv.DictReader`.
2. Build the classifier prompt from `institution`, `title` and `url` only. Add
   `institution_domain` only in an A/B variant. Tell the model that title and
   URL are untrusted data; row O22 is the kind of page that could carry injected
   text.
3. Parse the model's output into `type` and `might_match_institution` and reject
   values outside the allowed sets.
4. Compare with the expected columns using the rules in Section 4, skipping
   `any`.
5. Aggregate overall and by `case` and `confidence`.

Deterministic baseline for the institution field: a host check (`host == domain`
or `host` ends with `.` plus the domain), using the full domain and never the
last two labels, because `lccc.wy.edu` would collapse to `wy.edu`. On this set
it matches 25 of the 40 scored rows, all expected `yes`. The 15 off-domain rows
are 9 `no` and 6 `yes` (C01, C08, S03, S10, O04, O05), which is where a model is
actually needed.

Do not copy rows from this file into the classifier prompt as few-shot examples.
The three spec examples (C01, S01, S02) are in here; if any are used as few-shot
examples, drop them from the eval.

When adding rows, label the institution first (look for a named different school
in the host, subdomain or title), then the type (is the subject one club, many
clubs, or something else; is it TTRPG related), and tag `confidence` as
`judgment` whenever a second labeler might disagree.

## 7. Worked examples

- `S01`: institution `University of Connecticut`, title `Tabletop Gaming Club`,
  url `https://uconntact.uconn.edu/organization/tabletop_gaming_club`. Expected
  `single_club` and `yes` (case `ttrpg_club_page`). Title and slug name one
  TTRPG club; the school appears only as the nickname `uconn` in the host.
- `S02` and `S03`: title `Tabletop RPG Club - UMass Campus Pulse`, url
  `https://umassamherst.campuslabs.com/engage/organization/tabletop`. With
  institution `Massachusetts Institute of Technology` the expected result is
  `single_club` and `no`. With `University of Massachusetts Amherst` it is
  `single_club` and `yes`. Title and subdomain both name UMass.
- `S10`: institution `Concordia University Irvine`, title
  `Dungeons and Dragons Club`, url `https://hub.concordia.edu/DnDClub`. Expected
  `single_club` and `yes`, although the page belongs to a different Concordia.
  Unresolvable without the institution's domain.
- `N03`: institution `Catawba Valley Community College`, title
  `Roll For Initiative`, url `https://cvcc.edu/?p=2682`. Expected `not_sure` and
  `yes`. The title is TTRPG-flavored and the URL is opaque; answering `other`
  would be a hard fail.
- `O22`: institution `Boston University`, title
  `Roll For Initiative: Boston University's DnD Community Invites You On An Extraordinary Quest`,
  url
  `https://admin.store.motogp.com/roll-for-initiative-boston-universitys-dn-d-community-invites-you-on-an-extraordinary-quest`.
  Expected `other` and `any`. The title names the school and sounds like a club;
  the host is an unrelated retailer.

## 8. Known limitations

- Title fidelity: the 28 `web_search` titles are as returned by a search tool
  and may differ from what Tavily returns (suffixes stripped, slug fallbacks
  such as S12 and C09). Re-join titles by URL from the pipeline's own Stage 1
  CSV when exact fidelity matters.
- Institution names and `institution_domain` values are best-knowledge, not
  checked against Stage 0 output.
- Small and unrepresentative: 49 rows, 17 of them judgment calls, about half
  keep-worthy.
- Spec-dependent labels: O10 to O12 (non-TTRPG clubs), S10 (undetectable wrong
  school) and the `not_sure` rows (labeled by what is determinable, not by true
  page content).
- Pages change and URLs can rot; re-verify before relying on any single row.
