# Stage 0 — `build_institution_dataset.py`

**Output:** `data/institutions.csv`

Pulls only the relevant columns from the IPEDS database and writes them to a CSV. This is the seed list every later stage iterates over — mistakes here propagate through the whole pipeline (Stage 1 will happily generate 3 good search queries for a wrong or collapsed institution row).

## Things to get right at this stage

- **Multi-campus systems** (SUNY, UC, Penn State, etc.) — keep each campus as its own row with its own name. If the pull collapses these to the system name, Stage 1's search queries will target the wrong (or a nonexistent) page, and there's no fixing it downstream without re-running this stage.
- **`WEBADDR` is captured but is not a usable domain filter downstream.** It's IPEDS's "official site" column, but club pages routinely live off that domain — on vendor platforms, subdomains, or elsewhere. Keep the column (it's still a useful signal), but don't treat it as ground truth. Full reasoning on why, and what Stage 1 does instead, is in [stage1-search.md](stage1-search.md).

No open gaps specific to this stage are tracked yet — if you find one, add it here rather than burying it in a commit message.
