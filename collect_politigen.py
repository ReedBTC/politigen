"""
GenGov Data Collector
Generates all data needed by politigen.html.

Run from the repo root:
    python collect_politigen.py

Outputs (written to data/):
    data/congress_historical.csv       — one row per Congress (57th–119th, 1901–2025)
                                         generational %, mean/median age, senate/house age
    data/congress_snapshots_detail.csv — per-generation stats at 4 snapshot years
    data/bls_gen_comparison.csv        — generational share % by BLS sector + officials
"""

import io
import os
import requests
import pandas as pd
from datetime import date

# ── OUTPUT DIRECTORY ──────────────────────────────────────────────────────────
# All CSVs go into data/, relative to wherever this script is run from.
# Running from repo root (python collect_politigen.py) puts them in data/.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── GENERATIONAL CUTOFFS (Strauss-Howe) ───────────────────────────────────────
GENERATIONS = [
    ("Pre-G.I.",             1800, 1900),
    ("G.I. Generation",      1901, 1924),
    ("Silent Generation",    1925, 1942),
    ("Baby Boom Generation", 1943, 1960),
    ("Gen X (13ers)",        1961, 1981),
    ("Millennial Generation",1982, 2005),
    ("Gen Z",                2006, 2029),
]

def classify_generation(birth_year):
    if not birth_year:
        return None
    for name, start, end in GENERATIONS:
        if start <= birth_year <= end:
            return name
    return None

def parse_birth_year(dob_str):
    if not dob_str:
        return None
    try:
        return int(str(dob_str)[:4])
    except:
        return None

def age_at_date(dob_str, ref_date):
    """Age in whole years at ref_date (a date object)."""
    if not dob_str or len(dob_str) < 4:
        return None
    try:
        by = int(dob_str[:4])
        bm = int(dob_str[5:7]) if len(dob_str) >= 7 else 6
        bd = int(dob_str[8:10]) if len(dob_str) >= 10 else 1
        born = date(by, bm, bd)
        return ref_date.year - born.year - (
            (ref_date.month, ref_date.day) < (born.month, born.day)
        )
    except:
        return None

def congress_start_year(cn):
    """57th Congress started 1901; each congress is 2 years."""
    return 1901 + (cn - 57) * 2


# ══════════════════════════════════════════════════════════════════════════════
# PART 1: CONGRESS HISTORICAL  (HTML sections 1, 2, 3)
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 60)
print("PART 1: Congress historical data")
print("=" * 60)

print("\nDownloading legislator data (~15MB)...")
hist_url = "https://unitedstates.github.io/congress-legislators/legislators-historical.json"
curr_url = "https://unitedstates.github.io/congress-legislators/legislators-current.json"

hist = requests.get(hist_url, timeout=60).json()
curr = requests.get(curr_url, timeout=30).json()
all_legs = hist + curr
print(f"  → {len(all_legs):,} total legislators loaded")

START_CN, END_CN = 57, 119   # 1901 → 2025

# Build one row per (legislator × congress they served in)
rows = []
for leg in all_legs:
    bio   = leg.get("bio", {})
    name  = leg.get("name", {})
    dob   = bio.get("birthday", "")
    by    = parse_birth_year(dob)
    gen   = classify_generation(by)
    fname = f"{name.get('first','')} {name.get('last','')}".strip()

    for term in leg.get("terms", []):
        chamber   = term.get("type", "")       # 'sen' or 'rep'
        start_str = term.get("start", "")
        end_str   = term.get("end", "")
        if not start_str:
            continue
        ts = int(start_str[:4])
        te = int(end_str[:4]) if end_str else ts + 2

        for cn in range(START_CN, END_CN + 1):
            cy  = congress_start_year(cn)
            cy2 = cy + 2
            if ts <= cy2 and te >= cy:
                ref = date(cy, 1, 3)
                rows.append({
                    "congress":   cn,
                    "year":       cy,
                    "name":       fname,
                    "chamber":    "Senate" if chamber == "sen" else "House",
                    "dob":        dob,
                    "birth_year": by,
                    "generation": gen,
                    "age":        age_at_date(dob, ref),
                })

member_df = pd.DataFrame(rows)
member_df = member_df.drop_duplicates(subset=["congress", "name", "chamber"])
print(f"  → {len(member_df):,} member-congress records")

# ── Summary row per Congress ───────────────────────────────────────────────────
TRACKED_GENS = [
    "Pre-G.I.",
    "G.I. Generation",
    "Silent Generation",
    "Baby Boom Generation",
    "Gen X (13ers)",
    "Millennial Generation",
]

def safe_key(g):
    return g.replace(" ", "_").replace(".", "").replace("(", "").replace(")", "").replace("-", "").lower()

snapshots = []
for cn, grp in member_df.groupby("congress"):
    year   = congress_start_year(cn)
    total  = len(grp)
    ages   = grp["age"].dropna()
    senate = grp[grp["chamber"] == "Senate"]["age"].dropna()
    house  = grp[grp["chamber"] == "House"]["age"].dropna()

    row = {
        "congress":        cn,
        "year":            year,
        "total_members":   total,
        "mean_age":        round(ages.mean(), 1)    if len(ages)   else None,
        "median_age":      round(ages.median(), 1)  if len(ages)   else None,
        "senate_mean_age": round(senate.mean(), 1)  if len(senate) else None,
        "house_mean_age":  round(house.mean(), 1)   if len(house)  else None,
    }

    gen_counts = grp["generation"].value_counts()
    for g in TRACKED_GENS:
        row[f"pct_{safe_key(g)}"] = round(gen_counts.get(g, 0) / total * 100, 2)

    sen_grp    = grp[grp["chamber"] == "Senate"]
    sen_total  = len(sen_grp)
    sen_counts = sen_grp["generation"].value_counts()
    for g in TRACKED_GENS:
        row[f"senate_pct_{safe_key(g)}"] = (
            round(sen_counts.get(g, 0) / sen_total * 100, 2) if sen_total else 0
        )

    snapshots.append(row)

hist_df = pd.DataFrame(snapshots).sort_values("year")

# ── Snapshot detail rows  (Section 3 cards: 1965 / 1985 / 2005 / 2025) ────────
SNAP_YEARS    = [1965, 1985, 2005, 2025]
SNAP_GENS     = ["G.I. Generation", "Silent Generation",
                 "Baby Boom Generation", "Gen X (13ers)", "Millennial Generation"]
SNAP_GEN_KEYS = ["gi", "silent", "boomer", "genx", "millennial"]

snap_rows = []
for year in SNAP_YEARS:
    cn_match = hist_df[hist_df["year"] == year]["congress"]
    if len(cn_match) == 0:
        print(f"  ⚠ No congress found for {year}, skipping")
        continue
    cn = int(cn_match.iloc[0])

    for chamber_name in ["Full Congress", "Senate"]:
        sub = (member_df[member_df["congress"] == cn]
               if chamber_name == "Full Congress"
               else member_df[(member_df["congress"] == cn) & (member_df["chamber"] == "Senate")])
        total = len(sub)
        for gen, gkey in zip(SNAP_GENS, SNAP_GEN_KEYS):
            g_sub = sub[sub["generation"] == gen]
            if len(g_sub) == 0:
                continue
            snap_rows.append({
                "year":       year,
                "chamber":    chamber_name,
                "generation": gen,
                "gen_key":    gkey,
                "n":          len(g_sub),
                "mean_age":   round(g_sub["age"].dropna().mean(), 1) if len(g_sub["age"].dropna()) else None,
                "pct":        round(len(g_sub) / total * 100, 1),
            })

snap_df = pd.DataFrame(snap_rows)

# ── Save ───────────────────────────────────────────────────────────────────────
hist_df.to_csv(os.path.join(DATA_DIR, "congress_historical.csv"), index=False)
snap_df.to_csv(os.path.join(DATA_DIR, "congress_snapshots_detail.csv"), index=False)
print(f"\n✅ data/congress_historical.csv        — {len(hist_df)} rows")
print(f"✅ data/congress_snapshots_detail.csv  — {len(snap_df)} rows")


# ══════════════════════════════════════════════════════════════════════════════
# PART 2: BLS WORKFORCE COMPARISON  (HTML section 0)
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 2: BLS workforce generational comparison")
print("=" * 60)

# BLS sector search string → display label
SECTORS = {
    "Total, 16 years":           "All Workers",
    "Agriculture":               "Agriculture",
    "Mining":                    "Mining",
    "Construction":              "Construction",
    "Manufacturing":             "Manufacturing",
    "Wholesale":                 "Wholesale Trade",
    "Retail":                    "Retail Trade",
    "Transportation":            "Transportation",
    "Information":               "Information/Tech",
    "Finance":                   "Finance",
    "Professional and business": "Professional Svc",
    "Education and health":      "Education & Health",
    "Leisure and hospitality":   "Leisure & Hosp.",
    "Public administration":     "Gov't Workers",
}

print("\nDownloading BLS Table 18b (industry × age)...")
BLS_URL = "https://www.bls.gov/cps/cpsaat18b.xlsx"
resp = requests.get(BLS_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
resp.raise_for_status()
print(f"  → {len(resp.content) / 1024:.0f} KB downloaded")

raw = pd.read_excel(io.BytesIO(resp.content), sheet_name=0, header=None)

# Auto-detect header row
header_row = None
for i, row in raw.iterrows():
    rs = " ".join([str(v) for v in row])
    if "Total" in rs and ("16" in rs or "20" in rs):
        header_row = i
        break
if header_row is None:
    header_row = 4
print(f"  → Header detected at row {header_row}")

df_bls = pd.read_excel(io.BytesIO(resp.content), sheet_name=0, header=header_row)

col_map = {}
for col in df_bls.columns:
    cs = str(col).strip().lower()
    if "industry" in cs or cs == "unnamed: 0":  col_map[col] = "industry"
    elif "16" in cs and "19" in cs:             col_map[col] = "age_16_19"
    elif "20" in cs and "24" in cs:             col_map[col] = "age_20_24"
    elif "25" in cs and "34" in cs:             col_map[col] = "age_25_34"
    elif "35" in cs and "44" in cs:             col_map[col] = "age_35_44"
    elif "45" in cs and "54" in cs:             col_map[col] = "age_45_54"
    elif "55" in cs and "64" in cs:             col_map[col] = "age_55_64"
    elif "65" in cs:                            col_map[col] = "age_65_plus"
    elif "total" in cs:                         col_map[col] = "total"

df_bls = df_bls.rename(columns=col_map)
if "industry" not in df_bls.columns:
    df_bls = df_bls.rename(columns={df_bls.columns[0]: "industry"})
df_bls["industry"] = df_bls["industry"].astype(str).str.strip()
df_bls = df_bls[df_bls["industry"].notna() & (df_bls["industry"] != "nan")]

def pct_of_total(row, col):
    try:
        t = float(row.get("total", 0) or 0)
        v = float(row.get(col, 0) or 0)
        return round(v / t * 100, 1) if t else 0
    except:
        return 0

def bls_to_gen_shares(under25, a2544, a4564, a65plus):
    """
    Approximate generational shares from BLS 10-year age brackets.
    Birth-year ↔ age-in-2025 mapping:
      Gen Z (2006+):      ~30% of the under-25 bracket
      Millennial (82-05): rest of under-25 + most of 25-44
      Gen X (61-81):      tail of 25-44 + most of 45-64
      Boomer (43-60):     tail of 45-64 + younger 65+
      Silent (25-42):     older 65+
    """
    genz       = under25  * 0.300
    millennial = under25  * 0.700 + a2544 * 0.900
    genx       = a2544    * 0.100 + a4564 * 0.950
    boomer     = a4564    * 0.050 + a65plus * 0.425
    silent     = a65plus  * 0.450
    pregi      = a65plus  * 0.125

    total = genz + millennial + genx + boomer + silent + pregi
    if total == 0:
        return {}
    return {
        "pct_genz":       round(genz       / total * 100, 1),
        "pct_millennial": round(millennial / total * 100, 1),
        "pct_genx":       round(genx       / total * 100, 1),
        "pct_boomer":     round(boomer     / total * 100, 1),
        "pct_silent":     round(silent     / total * 100, 1),
    }

bls_rows = []
for search, label in SECTORS.items():
    matches = df_bls[df_bls["industry"].str.contains(search, case=False, na=False)]
    if len(matches) == 0:
        print(f"  ⚠ No match for: '{search}'")
        continue
    row  = matches.iloc[0]
    u25  = pct_of_total(row, "age_16_19") + pct_of_total(row, "age_20_24")
    a2544 = pct_of_total(row, "age_25_34") + pct_of_total(row, "age_35_44")
    a4564 = pct_of_total(row, "age_45_54") + pct_of_total(row, "age_55_64")
    a65p  = pct_of_total(row, "age_65_plus")
    bls_rows.append({
        "sector":         label,
        "is_elected":     False,
        "is_all_workers": label == "All Workers",
        "pct_under_25":   u25,
        "pct_25_44":      a2544,
        "pct_45_64":      a4564,
        "pct_65_plus":    a65p,
        **bls_to_gen_shares(u25, a2544, a4564, a65p),
    })
    print(f"  ✓ {label}")

# ── Elected officials row (exact birth dates from legislators-current.json) ────
off_gens   = {"genz": 0, "millennial": 0, "genx": 0, "boomer": 0, "silent": 0, "pregi": 0}
total_off  = 0

for leg in curr:
    dob = leg.get("bio", {}).get("birthday", "")
    gen = classify_generation(parse_birth_year(dob))
    if gen is None:
        continue
    total_off += 1
    key_map = {
        "Gen Z": "genz", "Millennial Generation": "millennial",
        "Gen X (13ers)": "genx", "Baby Boom Generation": "boomer",
        "Silent Generation": "silent", "Pre-G.I.": "pregi",
    }
    if gen in key_map:
        off_gens[key_map[gen]] += 1

def opct(key):
    return round(off_gens[key] / total_off * 100, 1) if total_off else 0

bls_rows.append({
    "sector":         "Elected Officials",
    "is_elected":     True,
    "is_all_workers": False,
    "pct_under_25":   opct("genz"),
    "pct_25_44":      opct("millennial"),
    "pct_45_64":      opct("genx"),
    "pct_65_plus":    opct("boomer") + opct("silent") + opct("pregi"),
    "pct_genz":       opct("genz"),
    "pct_millennial": opct("millennial"),
    "pct_genx":       opct("genx"),
    "pct_boomer":     opct("boomer"),
    "pct_silent":     opct("silent"),
})
print(f"  ✓ Elected Officials (n={total_off})")

bls_df = pd.DataFrame(bls_rows)
bls_df.to_csv(os.path.join(DATA_DIR, "bls_gen_comparison.csv"), index=False)
print(f"\n✅ data/bls_gen_comparison.csv  — {len(bls_df)} rows")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("ALL DONE")
print(f"  data/congress_historical.csv       — {len(hist_df)} congress rows")
print(f"  data/congress_snapshots_detail.csv — {len(snap_df)} snapshot rows")
print(f"  data/bls_gen_comparison.csv        — {len(bls_df)} sector rows")
print("=" * 60)

print("\n── Sanity check: mean age ──")
print(f"  {int(hist_df.iloc[0]['year'])} → {hist_df.iloc[0]['mean_age']}  (expected ~48.3)")
print(f"  {int(hist_df.iloc[-1]['year'])} → {hist_df.iloc[-1]['mean_age']}  (expected ~58.5)")
