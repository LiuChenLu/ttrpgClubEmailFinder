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
from urllib.parse import urlparse

from config import EXCLUDED_INSTITUTION_NAMES_PATH, load_word_list

INPUT_DATA_PATH = Path("./data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb")
OUTPUT_DATA_PATH = Path("./data/institutions.csv")
HD_TABLE = "HD2024"
ENROLLMENT_TABLE = "DRVEF2024"
SIZE_COLUMN = "FTE"
SIZE_MINIMUMS = {1: 300, 2: 750, 3: 10000}
KEYWORD_SIZE_MAXIMUM = 1500
HARTFORD_LATITUDE = 41.763710
HARTFORD_LONGITUDE = -72.685097


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
    host = urlparse(
        "//" + re.sub(r"^\w+://", "", url.strip().lower())
    ).hostname
    return bool(host) and host.endswith(".edu")


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
        "UNITID", "INSTNM", "CITY", "LONGITUD", "LATITUDE", "WEBADDR",
        "CYACTIVE", "SECTOR", "ICLEVEL",
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

    excluded_terms = load_word_list(EXCLUDED_INSTITUTION_NAMES_PATH)
    if excluded_terms:
        pattern = r"\b(?:" + "|".join(map(re.escape, excluded_terms)) + r")\b"
        keyword_hit = result["INSTNM"].str.contains(
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

    result = result.rename(columns={"UNITID":"unitid", "INSTNM": "college_name", "CITY": "city", "DISTANCE": "distance", "WEBADDR": "website"})
    result = result[["unitid", "college_name", "city", "distance", "website"]]
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