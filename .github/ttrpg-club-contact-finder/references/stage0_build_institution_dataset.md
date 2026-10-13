# Stage 0 — `build_institution_dataset.py`

**Output:** `data/institutions.csv`

Pulls only the relevant columns from the IPEDS database and writes them to a CSV. This is the seed list every later stage iterates over — mistakes here propagate through the whole pipeline.

## Things to get right at this stage

- **Multi-campus systems** (SUNY, UC, Penn State, etc.) — keep each campus as its own row with its own name.
- **`WEBADDR` is captured but is not a reliable domain filter downstream.** It's IPEDS's "official site" column, but club pages routinely live off that domain — on vendor platforms, subdomains, or elsewhere. Keep the column (it's still a useful signal since sometimes club pages are hosted on webaddr for smaller institutions). Full reasoning on why, and what Stage 1 does instead, is in [stage1_fetch_candidates.md](stage1_fetch_candidates.md).
- **Filtering out institutions that likely do not have a TTRPT club.** Filtering is coarsely tuned according to the following rules, which cuts the number of institutions by about 50%. If an institution matches any of these rules, it is filtered out. Negative FTE values are treated as missing; missing FTE does not trigger a size-based rule.
  - Inactive: CYACTIVE is not 1.
  - Administrative unit: SECTOR is 0.
  - Not .edu: the website host does not end in .edu.
  - Too small for its level: FTE is below the threshold: 
    - 300 for level 1 (schools offering 4 or more year programs)
    - 750 for level 2 (schools offering at least 2 but less than 4 years, usually community and associate-degree schools)
    - 10,000 for level 3 (schools offering less than 2 year programs, usually short term certificate or vocational schools). The threshold for level 3 is set such that we filter all level 3 institutions.
  - Trade or religion related name and small: the institution name or an IPEDS alias matches a keyword from excluded_institution_names.txt and FTE is below 1,500.

IPEDS's `IALIAS` value is normalized into the output `aliases` column using
`|` between aliases. Semicolons, commas, pipes, slashes, non-space whitespace
characters, and runs of two or more ordinary spaces separate aliases; a single
ordinary space remains within multi-word aliases. This column contains only
official IPEDS aliases. Generated shortened forms of institution names are
stored separately in the output `generated_aliases` column. Recognized
reductions remove a leading `University of`, a trailing `University` or
`College`, and produce both intermediate forms for names such as
`Appalachian University of Art` (`Appalachian University` and `Appalachian`).
They also remove a trailing `Community College`, remove periods from
abbreviations such as `St.`, and shorten `Massachusetts` to `Mass` (including
any institution-type reductions, e.g. `Massachusetts Jacobs University` adds
`Mass Jacobs University` and `Mass Jacobs`).
Generated aliases are deduplicated case-insensitively against IPEDS aliases.
Both official and generated aliases are included in the excluded-name keyword
check. After filtering, Stage 0 prints how many kept rows have aliases in
either column.

No open gaps specific to this stage are tracked yet — if you find one, add it here rather than burying it in a commit message.