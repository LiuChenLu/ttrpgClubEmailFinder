# Spec: alternative Stage 1 query templates

**Status:** draft. **Nothing in this file is implemented.** Only
`config/query_templates.txt` is read by the code. **Implements in:**
`config/query_templates.txt` (one template per line, with a `{name}`
placeholder). **Docs to update when it lands:**
`docs/stages/stage1_fetch_candidates.md` ("Scale & budget" template count).

These were moved out of `config/` because that folder holds only files the code
reads. Each extra template multiplies Stage 1's Tavily spend (2 credits per
search at `advanced` depth), so compare result quality before adding any.

```
{name} tabletop gaming club
{name} tabletop gaming board game ttrpg d&d role playing club
{name} board game club game night
{name} TTRPG D&D role playing club
{name} gaming club student organization
{name} student clubs and organizations list
```

The second line is the template in use today.
