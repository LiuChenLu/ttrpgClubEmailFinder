# This processes data from IPEDS.
# It reads the data from "./data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb".
# It outputs a CSV file that has one row per university campus.

from pathlib import Path
import pandas as pd
import subprocess
import csv
import io
from math import radians, sin, cos, asin, sqrt

INPUT_DATA_PATH = Path("./data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb")
OUTPUT_DATA_PATH = Path("./data/institutions.csv")
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


def has_edu_webaddr(webaddr: str) -> bool:
    """Return True if webaddr is non-empty and contains '.edu' as a substring."""
    return bool(webaddr) and ".edu" in webaddr.lower()


def read_ipeds():
    """Return the relevant HD2024 columns as a pandas DataFrame.

    Uses mdb-export rather than mdb-sql: mdb-sql has no field-quoting
    mechanism, so any institution name containing a literal comma (e.g.
    "First Institute of Travel, Inc.") silently corrupts a naive comma-split
    parse. mdb-export quotes text fields by default, so csv.DictReader can
    parse the output correctly regardless of embedded commas.
    """
    columns = ["UNITID", "INSTNM", "CITY", "LONGITUD", "LATITUDE", "WEBADDR"]

    completed = subprocess.run(
        ["mdb-export", "--null", "", str(INPUT_DATA_PATH), "HD2024"],
        check=True,
        capture_output=True,
        text=True,
    )

    rows = list(csv.DictReader(io.StringIO(completed.stdout)))
    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(rows)[columns]


def process_ipeds(df):
    """Normalize the IPEDS dataframe and compute each campus's distance from Hartford."""
    result = df.copy()

    result["UNITID"] = pd.to_numeric(result["UNITID"], errors="coerce")
    result["LONGITUD"] = pd.to_numeric(result["LONGITUD"], errors="coerce")
    result["LATITUDE"] = pd.to_numeric(result["LATITUDE"], errors="coerce")
    result["WEBADDR"] = result["WEBADDR"].fillna("").astype(str).str.strip()

    edu_mask = result["WEBADDR"].apply(has_edu_webaddr)
    dropped = int((~edu_mask).sum())
    if dropped:
        print(f"Dropping {dropped} institution(s) without a .edu WEBADDR")
    result = result[edu_mask]

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