import csv
import random
from pathlib import Path

input_file = Path("./data/institutions.csv")
output_file = Path("./data/institutions_sample.csv")
sample_size = 3

with open(input_file, newline="", encoding="utf-8") as f:
    reader = list(csv.DictReader(f))

sample = random.sample(reader, sample_size)

with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=reader[0].keys())
    writer.writeheader()
    writer.writerows(sample)

print(f"Sampled {len(sample)} rows to {output_file}")