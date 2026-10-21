# This processes data from IPEDS.
# It reads the data from "./data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb".
# It outputs a CSV file that has one row per university campus.

from pathlib import Path
import pandas as pd
import subprocess
import csv
import io
import re
from math import radians, sin, cos, asin, sqrt

from config import (
    EXCLUDED_INSTITUTION_NAMES_PATH,
    HARTFORD_LATITUDE,
    HARTFORD_LONGITUDE,
    INSTITUTIONS_CSV,
    IPEDS_DB_PATH,
    IPEDS_ENROLLMENT_TABLE as ENROLLMENT_TABLE,
    IPEDS_HD_TABLE as HD_TABLE,
    IPEDS_SIZE_COLUMN as SIZE_COLUMN,
    KEYWORD_SIZE_MAXIMUM,
    SIZE_MINIMUMS,
    load_word_list,
)
from schema import INSTITUTION_FIELDNAMES
from url_parsing_utils import extract_host

INPUT_DATA_PATH = Path(IPEDS_DB_PATH)
OUTPUT_DATA_PATH = Path(INSTITUTIONS_CSV)


def distance(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a)) 

    return R * c


def is_edu(url):
    if pd.isna(url):
        return False
    host = extract_host(url)
    return host is not None and host.endswith(".edu")


def normalize_aliases(aliases):
    """Normalize IPEDS aliases to pipe-delimited values."""
    if pd.isna(aliases):
        return ""

    parts = re.split(r"(?:[;,|/]|[\t\r\n\f\v]+| {2,})+", str(aliases))
    return "|".join(alias.strip() for alias in parts if alias.strip())


def generate_aliases(institution_name, ipeds_aliases=""):
    """Generate shortened name forms not already present in IPEDS aliases."""
    existing_aliases = normalize_aliases(ipeds_aliases).split("|")
    generated = []
    name = "" if pd.isna(institution_name) else str(institution_name).strip()

    name_variants = [name]

    # Example: "St. John" -> "St John".
    without_abbreviation_dots = re.sub(r"\b([A-Za-z]+)\.", r"\1", name)
    if without_abbreviation_dots != name:
        name_variants.append(without_abbreviation_dots)

    # Example: "Massachusetts Jacobs University" -> "Mass Jacobs University".
    name_variants.extend(
        short_name
        for variant in name_variants.copy()
        if (short_name := re.sub(
            r"\bMassachusetts\b", "Mass", variant, flags=re.IGNORECASE
        )) != variant
    )

    for variant in name_variants:
        if variant != name:
            generated.append(variant)

        leading_university_of = re.fullmatch(
            r"University of\s+(.+)", variant, flags=re.IGNORECASE
        )
        if leading_university_of:
            # Example: "University of Richmond" -> "Richmond".
            generated.append(leading_university_of.group(1).strip())

        university_of_phrase = re.fullmatch(
            r"(.+?)\s+University of\s+.+", variant, flags=re.IGNORECASE
        )
        if university_of_phrase:
            base_name = university_of_phrase.group(1).strip()
            # Example: "Appalachian University of Art" -> "Appalachian University".
            # Also add the shorter base form: "Appalachian".
            generated.extend((f"{base_name} University", base_name))

        community_college = re.sub(
            r"\s+Community College$", "", variant, flags=re.IGNORECASE
        ).strip()
        if community_college != variant:
            # Example: "Mass Bay Community College" -> "Mass Bay".
            generated.append(community_college)
        else:
            trailing_institution_type = re.sub(
                r"\s+(?:University|College)$", "", variant, flags=re.IGNORECASE
            ).strip()
            if trailing_institution_type != variant:
                # Examples: "Faulkner University" -> "Faulkner"; "Bethany College" -> "Bethany".
                generated.append(trailing_institution_type)

    aliases = []
    seen = set()
    existing = {alias.casefold() for alias in existing_aliases if alias}
    for alias in generated:
        alias = alias.strip()
        if alias and alias.casefold() not in existing and alias.casefold() not in seen:
            aliases.append(alias)
            seen.add(alias.casefold())
    return "|".join(aliases)


def read_ipeds():
    """Load institution data and merge FTE enrollment by UNITID."""
    hd = read_ipeds_table(HD_TABLE)
    enrollment = read_ipeds_table(ENROLLMENT_TABLE)
    if SIZE_COLUMN not in enrollment.columns:
        raise ValueError(
            f"{SIZE_COLUMN} not in {ENROLLMENT_TABLE}; "
            f"columns: {list(enrollment.columns)}"
        )

    columns = [
        "UNITID", "INSTNM", "IALIAS", "CITY", "LONGITUD", "LATITUDE",
        "WEBADDR", "CYACTIVE", "SECTOR", "ICLEVEL",
    ]
    return hd[columns].merge(
        enrollment[["UNITID", SIZE_COLUMN]], on="UNITID", how="left"
    )


def read_ipeds_table(table):
    """Export an IPEDS table with quoted fields parsed by pandas."""
    completed = subprocess.run(
        ["mdb-export", "--null", "", str(INPUT_DATA_PATH), table],
        check=True,
        capture_output=True,
        text=True,
    )
    result = pd.read_csv(io.StringIO(completed.stdout), low_memory=False)
    result.columns = result.columns.str.upper()
    return result


def process_ipeds(df):
    """Normalize the IPEDS dataframe and compute each campus's distance from Hartford."""
    result = df.copy()

    result["UNITID"] = pd.to_numeric(result["UNITID"], errors="coerce")
    result["LONGITUD"] = pd.to_numeric(result["LONGITUD"], errors="coerce")
    result["LATITUDE"] = pd.to_numeric(result["LATITUDE"], errors="coerce")
    result["CYACTIVE"] = pd.to_numeric(result["CYACTIVE"], errors="coerce")
    result["SECTOR"] = pd.to_numeric(result["SECTOR"], errors="coerce")
    result["ICLEVEL"] = pd.to_numeric(result["ICLEVEL"], errors="coerce")
    size = pd.to_numeric(result[SIZE_COLUMN], errors="coerce")
    size = size.where(size >= 0)
    result[SIZE_COLUMN] = size
    result["IALIAS"] = result["IALIAS"].map(normalize_aliases)
    result["GENERATED_ALIASES"] = [
        generate_aliases(name, aliases)
        for name, aliases in zip(result["INSTNM"], result["IALIAS"])
    ]

    excluded_terms = load_word_list(EXCLUDED_INSTITUTION_NAMES_PATH)
    if excluded_terms:
        pattern = r"\b(?:" + "|".join(map(re.escape, excluded_terms)) + r")\b"
        institution_names = (
            result["INSTNM"].fillna("").astype(str)
            + " "
            + result["IALIAS"].fillna("").astype(str)
            + " "
            + result["GENERATED_ALIASES"].fillna("").astype(str)
        )
        keyword_hit = institution_names.str.contains(
            pattern, case=False, regex=True, na=False
        )
    else:
        keyword_hit = pd.Series(False, index=result.index)

    rules = {
        "inactive": result["CYACTIVE"] != 1,
        "admin unit": result["SECTOR"] == 0,
        "not .edu": ~result["WEBADDR"].map(is_edu),
        "small for level": size < result["ICLEVEL"].map(SIZE_MINIMUMS),
        "trade keyword + small": keyword_hit & (size < KEYWORD_SIZE_MAXIMUM),
    }
    for name, mask in rules.items():
        count = int(mask.sum())
        if count:
            print(f"Dropping {count} institution(s): {name}")

    drop_mask = pd.concat(rules.values(), axis=1).any(axis=1)
    if drop_mask.any():
        print(f"Dropping {int(drop_mask.sum())} institution(s) total")
    result = result[~drop_mask].copy()
    alias_count = int(
        (result["IALIAS"].ne("") | result["GENERATED_ALIASES"].ne("")).sum()
    )
    print(f"Kept rows with aliases: {alias_count} of {len(result)}")

    coords_mask = result["LONGITUD"].notna() & result["LATITUDE"].notna()
    result["DISTANCE"] = pd.NA
    result.loc[coords_mask, "DISTANCE"] = result.loc[coords_mask].apply(
        lambda row: distance(
            row["LATITUDE"],
            row["LONGITUD"],
            HARTFORD_LATITUDE,
            HARTFORD_LONGITUDE,
        ),
        axis=1,
    )

    result = result.rename(columns={
        "UNITID": "unitid", "INSTNM": "college_name", "IALIAS": "aliases",
        "GENERATED_ALIASES": "generated_aliases",
        "CITY": "city", "DISTANCE": "distance", "WEBADDR": "website",
    })
    result = result[INSTITUTION_FIELDNAMES]
    result = result.sort_values(
        ["distance", "unitid"], na_position="last", kind="mergesort"
    )

    return result


def main():
    df = read_ipeds()
    df = process_ipeds(df)

    OUTPUT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DATA_PATH, index=False, quoting=csv.QUOTE_MINIMAL)


if __name__ == '__main__':
    main()