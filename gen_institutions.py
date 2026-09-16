# This processes data from IPEDS.
# It reads the data from "./data/ipeds/IPEDS_2024-25_Provisional/IPEDS202425.accdb".
# It outputs a CSV file that has one row per university campus.

from pathlib import Path
import pandas as pd
import subprocess
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

def read_ipeds():
    """Return the relevant HD2024 columns as a pandas DataFrame."""
    columns = ["UNITID", "INSTNM", "CITY", "LONGITUD", "LATITUDE", "WEBADDR"]
    query = "SELECT UNITID, INSTNM, CITY, LONGITUD, LATITUDE, WEBADDR FROM HD2024;"

    completed = subprocess.run(
        ["mdb-sql", "-P", "-d", ",", str(INPUT_DATA_PATH)],
        check=True,
        capture_output=True,
        text=True,
        input=query,
    )

    lines = [line.rstrip("\n") for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        return pd.DataFrame(columns=columns)

    rows = []
    for line in lines[1:]:
        parts = line.split(",", 5)
        if len(parts) != 6:
            continue

        row = {columns[i]: parts[i].strip() for i in range(len(columns))}
        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def process_ipeds(df):
    """Normalize the IPEDS dataframe and compute each campus's distance from Hartford."""
    result = df.copy()

    result["UNITID"] = pd.to_numeric(result["UNITID"], errors="coerce")
    result["LONGITUD"] = pd.to_numeric(result["LONGITUD"], errors="coerce")
    result["LATITUDE"] = pd.to_numeric(result["LATITUDE"], errors="coerce")
    result["WEBADDR"] = result["WEBADDR"].fillna("").astype(str).str.strip()

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

    result = result.rename(columns={"INSTNM": "NAME", "WEBADDR": "WEBSITE"})
    result = result[["UNITID", "NAME", "CITY", "DISTANCE", "WEBSITE"]]
    result = result.sort_values(
        ["DISTANCE", "UNITID"], na_position="last", kind="mergesort"
    )

    return result


def main():
    df = read_ipeds()
    df = process_ipeds(df)

    OUTPUT_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DATA_PATH, index=False)


if __name__ == '__main__':
    main()