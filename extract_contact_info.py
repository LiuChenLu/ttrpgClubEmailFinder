"""Stage 4: derive contact signals from stage 3's CSV. Makes no network calls.

For each row, the text gate is re-derived from stage 3's columns: both
club_keywords_found_in_text AND ttrpg_keywords_found_in_text must be non-empty.
Rows that fail it are written through with the three new columns blank/false
and are never scanned. Every input row produces exactly one output row.

Usage:
    python extract_contact_info.py
"""

from __future__ import annotations

import csv
import re

from config import DEFAULT_CONTACTS_CSV, DEFAULT_FILTERED_CSV

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}")
DISCORD_RE = re.compile(r"(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+")

# Bare words, deliberately separate from the regexes above: a page can invite
# contact through a mail form or behind a human-verification step without ever
# putting an address in the text, and those are the rows worth a human look.
CONTACT_WORD_RE = re.compile(
    r"\b(?:contacts?|emails?|discord|enquiry|enquiries|messages?)\b", re.IGNORECASE
)

# TODO: revisit this word list. The words vary a lot in how specifically they
# signal an actual contact channel — "email"/"discord" are strong, "enquiry"
# is decent, "message"/"contact" are generic enough to fire on unrelated page
# content (e.g. "message from the president"). Right now they're all folded
# into one bool; consider splitting into tiers (e.g. strong/weak signal, or a
# count of distinct words matched) so has_contact_signal can be weighted or
# filtered by confidence instead of being all-or-nothing.

NEW_FIELDNAMES = ["has_contact_signal", "email_found", "discord_found"]

NOT_SCANNED = {"has_contact_signal": False, "email_found": "", "discord_found": ""}

# Stage 1 writes whole pages into result_raw_content, well past csv's default
# 131072-char field cap. sys.maxsize overflows C long on some platforms, so use
# a value that is large enough for any page and portable.
csv.field_size_limit(2**31 - 1)

# TODO: try to find a contact name.
# TODO: distinguish multiple emails (club president vs. club group address).


def passes_text_gate(row: dict) -> bool:
    """AND across the two lists, unlike stage 3's OR over the snippet."""
    return bool(
        row.get("club_keywords_found_in_text", "").strip()
        and row.get("ttrpg_keywords_found_in_text", "").strip()
    )


def contact_columns(raw_content: str, snippet: str) -> dict:
    """Emails come from the page text and the snippet; Discord only from text.

    The snippet is worth scanning because it survives a failed extraction, but
    it's truncated to SNIPPET_CHARS, so treat it as a supplement.
    """
    emails = EMAIL_RE.findall(raw_content) + EMAIL_RE.findall(snippet)
    emails = list(dict.fromkeys(emails))
    discord_links = DISCORD_RE.findall(raw_content)
    return {
        "has_contact_signal": bool(
            emails or discord_links or CONTACT_WORD_RE.search(raw_content)
        ),
        "email_found": "; ".join(emails),
        "discord_found": "; ".join(discord_links),
    }


def main(
    input_csv: str = DEFAULT_FILTERED_CSV, output_csv: str = DEFAULT_CONTACTS_CSV
) -> None:
    with open(input_csv, newline="", encoding="utf-8") as f_in, \
         open(output_csv, "w", newline="", encoding="utf-8") as f_out:

        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out,
                                fieldnames=NEW_FIELDNAMES if reader.fieldnames is None 
                                           else list(reader.fieldnames) + NEW_FIELDNAMES)
        writer.writeheader()

        for row in reader:
            if passes_text_gate(row):
                row.update(contact_columns(
                    row.get("result_raw_content", ""),
                    row.get("result_snippet", ""),
                ))
            else:
                row.update(NOT_SCANNED)
            writer.writerow(row)


if __name__ == "__main__":
    main()