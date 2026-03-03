"""
Politigen Data Collector
Generates all data needed by index.html.

Run from the repo root:
    python collect_politigen.py

Outputs (written to data/):
    data/congress_historical.csv       — one row per Congress (57th–119th, 1901–2025)
                                         generational %, mean/median age, senate/house age
    data/congress_snapshots_detail.csv — per-generation stats at 4 snapshot years
    data/bls_gen_comparison.csv        — generational share % by BLS sector + officials
    data/presidents.csv                — one row per presidential term start since 1901
    data/senators_2026.csv             — ALL 2026 ballot incumbents (Senate Class II +
                                         top-65 House members by age), with tenure,
                                         generation, re-election status, and a `chamber`
                                         column ("Senate" or "House") for UI filtering.
                                         House capped at HOUSE_WALL_CAP: all retirees
                                         + oldest seekers by birth year.
                                         House rows also include a `district` column.
"""

import io
import os
import requests
import pandas as pd
from datetime import date

# ── OUTPUT DIRECTORY ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── GENERATIONAL CUTOFFS (Strauss-Howe) ───────────────────────────────────────
GENERATIONS = [
    ("Pre-G.I.",               1800, 1842),   # fallback only
    ("Progressive Generation", 1843, 1859),
    ("Missionary Generation",  1860, 1882),
    ("Lost Generation",        1883, 1900),
    ("G.I. Generation",        1901, 1924),
    ("Silent Generation",      1925, 1942),
    ("Baby Boom Generation",   1943, 1960),
    ("Gen X (13ers)",          1961, 1981),
    ("Millennial Generation",  1982, 2005),
    ("Gen Z",                  2006, 2029),
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
        chamber   = term.get("type", "")
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
    "Progressive Generation",
    "Missionary Generation",
    "Lost Generation",
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

    hou_grp    = grp[grp["chamber"] == "House"]
    hou_total  = len(hou_grp)
    hou_counts = hou_grp["generation"].value_counts()
    for g in TRACKED_GENS:
        row[f"house_pct_{safe_key(g)}"] = (
            round(hou_counts.get(g, 0) / hou_total * 100, 2) if hou_total else 0
        )

    snapshots.append(row)

hist_df = pd.DataFrame(snapshots).sort_values("year")

# ── Snapshot detail rows ────────────────────────────────────────────────────────
SNAP_YEARS = [1965, 1985, 2005, 2025]

SNAP_GENS = [
    "Progressive Generation",
    "Missionary Generation",
    "Lost Generation",
    "G.I. Generation",
    "Silent Generation",
    "Baby Boom Generation",
    "Gen X (13ers)",
    "Millennial Generation",
]
SNAP_GEN_KEYS = ["progressive", "missionary", "lost", "gi", "silent", "boomer", "genx", "millennial"]

snap_rows = []
for year in SNAP_YEARS:
    cn_match = hist_df[hist_df["year"] == year]["congress"]
    if len(cn_match) == 0:
        print(f"  ⚠ No congress found for {year}, skipping")
        continue
    cn = int(cn_match.iloc[0])

    for chamber_name in ["House", "Senate"]:
        sub = (member_df[(member_df["congress"] == cn) & (member_df["chamber"] == "House")]
               if chamber_name == "House"
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

print("\n── Sanity check: generations (House) ──")
for g in ["Progressive Generation", "Missionary Generation", "Lost Generation"]:
    key = f"pct_{safe_key(g)}"
    peak_row = hist_df.loc[hist_df[key].idxmax()]
    print(f"  {g}: peak {peak_row[key]:.1f}% in {int(peak_row['year'])}")


# ══════════════════════════════════════════════════════════════════════════════
# PART 2: BLS WORKFORCE COMPARISON  (HTML section 0)
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 2: BLS workforce generational comparison")
print("=" * 60)

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

# ── Elected officials row — built first so it appears at top of CSV ────────────
off_gens   = {"genz": 0, "millennial": 0, "genx": 0, "boomer": 0, "silent": 0, "pregi": 0}
total_off  = 0

for leg in curr:
    dob = leg.get("bio", {}).get("birthday", "")
    gen = classify_generation(parse_birth_year(dob))
    if gen is None:
        continue
    total_off += 1
    key_map = {
        "Gen Z":                  "genz",
        "Millennial Generation":  "millennial",
        "Gen X (13ers)":          "genx",
        "Baby Boom Generation":   "boomer",
        "Silent Generation":      "silent",
        "Lost Generation":        "pregi",
        "Missionary Generation":  "pregi",
        "Progressive Generation": "pregi",
        "Pre-G.I.":               "pregi",
    }
    if gen in key_map:
        off_gens[key_map[gen]] += 1

def opct(key):
    return round(off_gens[key] / total_off * 100, 1) if total_off else 0

bls_rows.append({
    "sector":         "Congress",
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

# ── BLS sector rows ────────────────────────────────────────────────────────────
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

bls_df = pd.DataFrame(bls_rows)
bls_df.to_csv(os.path.join(DATA_DIR, "bls_gen_comparison.csv"), index=False)
print(f"\n✅ data/bls_gen_comparison.csv  — {len(bls_df)} rows")


# ══════════════════════════════════════════════════════════════════════════════
# PART 3: PRESIDENTS  (HTML section 1 — dots on Rise & Fall curves)
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 3: Presidential terms since 1901")
print("=" * 60)

# One row per term start (including succession).
# Birth years sourced from historical record — fully static data.
# Display names: last name only, except Roosevelt and Bush which need
# disambiguation via initials.
#
# year        = year they took office (inauguration or succession)
# name        = display name for tooltip
# birth_year  = used to derive generation via classify_generation()
# how         = 'elected' | 'succession' — informational, not used in chart yet

PRESIDENT_DATA = [
    # --- Progressive Generation (born 1843–1859) ---
    {"year": 1901, "name": "T. Roosevelt",  "birth_year": 1858, "how": "succession"},  # McKinley assassinated
    {"year": 1905, "name": "T. Roosevelt",  "birth_year": 1858, "how": "elected"},
    {"year": 1909, "name": "Taft",          "birth_year": 1857, "how": "elected"},
    {"year": 1913, "name": "Wilson",        "birth_year": 1856, "how": "elected"},
    {"year": 1917, "name": "Wilson",        "birth_year": 1856, "how": "elected"},

    # --- Missionary Generation (born 1860–1882) ---
    {"year": 1921, "name": "Harding",       "birth_year": 1865, "how": "elected"},
    {"year": 1923, "name": "Coolidge",      "birth_year": 1872, "how": "succession"},  # Harding died
    {"year": 1925, "name": "Coolidge",      "birth_year": 1872, "how": "elected"},
    {"year": 1929, "name": "Hoover",        "birth_year": 1874, "how": "elected"},
    {"year": 1933, "name": "F. Roosevelt",  "birth_year": 1882, "how": "elected"},
    {"year": 1937, "name": "F. Roosevelt",  "birth_year": 1882, "how": "elected"},
    {"year": 1941, "name": "F. Roosevelt",  "birth_year": 1882, "how": "elected"},
    {"year": 1945, "name": "F. Roosevelt",  "birth_year": 1882, "how": "elected"},  # died same year

    # --- G.I. Generation (born 1901–1924) ---
    {"year": 1945, "name": "Truman",        "birth_year": 1884, "how": "succession"},  # FDR died — Truman born 1884 = Lost Gen actually
    {"year": 1949, "name": "Truman",        "birth_year": 1884, "how": "elected"},
    {"year": 1953, "name": "Eisenhower",    "birth_year": 1890, "how": "elected"},
    {"year": 1957, "name": "Eisenhower",    "birth_year": 1890, "how": "elected"},
    {"year": 1961, "name": "Kennedy",       "birth_year": 1917, "how": "elected"},
    {"year": 1963, "name": "Johnson",       "birth_year": 1908, "how": "succession"},  # JFK assassinated
    {"year": 1965, "name": "Johnson",       "birth_year": 1908, "how": "elected"},
    {"year": 1969, "name": "Nixon",         "birth_year": 1913, "how": "elected"},
    {"year": 1973, "name": "Nixon",         "birth_year": 1913, "how": "elected"},
    {"year": 1974, "name": "Ford",          "birth_year": 1913, "how": "succession"},  # Nixon resigned
    {"year": 1977, "name": "Carter",        "birth_year": 1924, "how": "elected"},
    {"year": 1981, "name": "Reagan",        "birth_year": 1911, "how": "elected"},
    {"year": 1985, "name": "Reagan",        "birth_year": 1911, "how": "elected"},

    # --- Silent Generation (born 1925–1942) ---
    {"year": 1989, "name": "G.H.W. Bush",  "birth_year": 1924, "how": "elected"},  # born 1924 = G.I. actually
    {"year": 1993, "name": "Clinton",       "birth_year": 1946, "how": "elected"},  # Boomer

    # --- Baby Boom Generation (born 1943–1960) ---
    {"year": 1997, "name": "Clinton",       "birth_year": 1946, "how": "elected"},
    {"year": 2001, "name": "G.W. Bush",     "birth_year": 1946, "how": "elected"},
    {"year": 2005, "name": "G.W. Bush",     "birth_year": 1946, "how": "elected"},
    {"year": 2009, "name": "Obama",         "birth_year": 1961, "how": "elected"},  # Gen X actually
    {"year": 2013, "name": "Obama",         "birth_year": 1961, "how": "elected"},
    {"year": 2017, "name": "Trump",         "birth_year": 1946, "how": "elected"},
    {"year": 2021, "name": "Biden",         "birth_year": 1942, "how": "elected"},  # Silent Gen actually
    {"year": 2025, "name": "Trump",         "birth_year": 1946, "how": "elected"},
]

# Derive generation from birth year using the same function as congress data
pres_rows = []
for p in PRESIDENT_DATA:
    gen = classify_generation(p["birth_year"])
    pres_rows.append({
        "year":       p["year"],
        "name":       p["name"],
        "birth_year": p["birth_year"],
        "generation": gen,
        "how":        p["how"],
    })

pres_df = pd.DataFrame(pres_rows)
pres_df.to_csv(os.path.join(DATA_DIR, "presidents.csv"), index=False)

print(f"\n✅ data/presidents.csv  — {len(pres_df)} rows")
print("\n── Sanity check: presidents by generation ──")
for gen, grp in pres_df.groupby("generation"):
    names = ", ".join(grp["name"].unique())
    print(f"  {gen}: {names}")


# ══════════════════════════════════════════════════════════════════════════════
# PART 4: 2026 SENATE ELECTIONS — CALCIFICATION WALL (Senate tab)
# (HTML section 4 — The Calcification Wall)
#
# Uses the `curr` legislators JSON already downloaded in Part 1.
# Identifies Class II senators (terms ending ~Jan 2027) and outputs
# one row per senator with tenure, generation, and re-election status.
# Adds chamber="Senate" and district="" for consistency with Part 5.
#
# Re-election status is determined dynamically by querying the FEC API
# for 2026 Senate incumbents who have filed as candidates. Any Class II
# senator whose state does NOT appear in the FEC filings is assumed to
# not be seeking re-election.
#
# The CSV write is deferred to after Part 5 so both chambers can be
# combined into a single senators_2026.csv file.
#
# FEC API docs: https://api.open.fec.gov/developers
# A free API key can be obtained at https://api.data.gov/signup
# The DEMO_KEY below works for low-volume use (~1000 req/hour per IP).
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 4: 2026 Senate elections — Calcification Wall")
print("=" * 60)

# ── Query FEC API for 2026 Senate incumbent filers ────────────────────────────
FEC_API_KEY = "DEMO_KEY"   # Replace with your key from api.data.gov/signup
FEC_URL     = "https://api.open.fec.gov/v1/candidates/"

print("\nUsing hardcoded retirement list for 2026 Senate Class II...")
# WHY NOT FEC API: The FEC incumbent_challenge=I query only returns senators who
# have formally filed paperwork. Early in the election cycle (e.g. March 2026)
# only 1-2 senators may have filed, so the API severely understates who is seeking
# re-election. Retirement announcements are the opposite -- they're national news,
# slow-moving, and finite. It's easier to maintain a list of the ~8 people NOT
# running than to wait for 25+ people to file paperwork.
#
# HOW TO MAINTAIN: When a new retirement is announced, add their state code and
# a dated comment. To verify the current list is complete, check:
#   https://ballotpedia.org/United_States_Senate_elections,_2026
#   (see "Incumbents retiring from public office" section)
#
# WARNING: Do not populate from memory -- verify against Ballotpedia directly.
#
# Last validated against Ballotpedia screenshot: 2026-03-02
# Confirmed retirees: 8 (four D, four R per table; prose count of 7 appears stale)
RETIRING_STATES = {
    "IA",   # Joni Ernst        -- announced Sept 2, 2025
    "IL",   # Dick Durbin       -- announced April 23, 2025
    "KY",   # Mitch McConnell   -- announced Feb 20, 2025
    "MI",   # Gary Peters       -- announced Jan 28, 2025
    "MN",   # Tina Smith        -- announced Feb 13, 2025
    "NC",   # Thom Tillis       -- announced June 29, 2025
    "NH",   # Jeanne Shaheen    -- announced March 12, 2025
    "WY",   # Cynthia Lummis    -- announced Dec 19, 2025
}
print(f"  → {len(RETIRING_STATES)} confirmed retirements: {sorted(RETIRING_STATES)}")
print("  → All other Class II incumbents defaulting to seeking=True")



# ── Identify Class II senators from the current legislators JSON ──────────────
# Class II senators have terms ending in January 2027.
# In the JSON, their most recent senate term end date will be "2027-01-03"
# or their term started in 2021 (last regular Class II election year).

def is_class_ii(leg):
    """Return True if this legislator is a current Class II senator.

    Uses the authoritative 'class' field (1, 2, or 3) present on every
    senate term in the unitedstates/congress-legislators JSON.  Falling
    back to date inference is unreliable: end dates lag for sitting members,
    and the start-date heuristic incorrectly catches Class III Georgia
    runoff senators (Warnock/Ossoff, started 2021-01) while missing Class II
    senators appointed mid-term after 2021.
    """
    terms = leg.get("terms", [])
    # Walk terms in reverse; evaluate only the most recent senate term.
    for term in reversed(terms):
        if term.get("type") != "sen":
            continue
        # Primary check: class field is always present and authoritative.
        if term.get("class") == 2:
            return True
        # Hard fallback (should rarely be needed): if class field is absent
        # for some reason, accept a term that explicitly ends Jan 2027.
        end = term.get("end", "")
        if end.startswith("2027-01"):
            return True
        # Most recent senate term is not Class II — stop looking.
        return False
    return False

def first_senate_year(leg):
    """Year the legislator first took a senate seat."""
    years = []
    for term in leg.get("terms", []):
        if term.get("type") == "sen":
            s = term.get("start", "")
            if s:
                try:
                    years.append(int(s[:4]))
                except:
                    pass
    return min(years) if years else None

def get_party(leg):
    """Most recent party affiliation."""
    for term in reversed(leg.get("terms", [])):
        p = term.get("party", "")
        if p:
            return p
    return "Unknown"

# ── Build the 2026 senate rows ─────────────────────────────────────────────────
sen26_rows = []

for leg in curr:
    terms = leg.get("terms", [])
    # Must have at least one senate term
    if not any(t.get("type") == "sen" for t in terms):
        continue
    # Must be Class II
    if not is_class_ii(leg):
        continue

    bio    = leg.get("bio", {})
    name   = leg.get("name", {})
    last   = name.get("last", "")
    first  = name.get("first", "")
    dob    = bio.get("birthday", "")
    by     = parse_birth_year(dob)
    gen    = classify_generation(by)

    # Most recent senate term for state and party
    most_recent_sen = None
    for term in reversed(terms):
        if term.get("type") == "sen":
            most_recent_sen = term
            break

    if not most_recent_sen:
        continue

    state  = most_recent_sen.get("state", "")
    party  = most_recent_sen.get("party", get_party(leg))
    since  = first_senate_year(leg)

    # Seeking = True for everyone EXCEPT confirmed retirements
    seeking = state not in RETIRING_STATES

    # Years served as of 2027 (end of current term)
    years_served = (2027 - since) if since else None

    # Age at end of NEXT term if re-elected (6 more years from 2027)
    age_now        = (2026 - by)       if by else None
    age_end_term   = (2033 - by)       if by else None  # end of next term

    sen26_rows.append({
        "last":             last,
        "first":            first,
        "state":            state,
        "district":         "",      # Senate seats have no district
        "party":            party,
        "born":             by,
        "generation":       gen,
        "since":            since,
        "years_served":     years_served,
        "seeking_reelection": seeking,
        "age_now":          age_now,
        "age_end_next_term": age_end_term,
        "chamber":          "Senate",
    })

# ── Sort: seeking re-election first, then by tenure desc ──────────────────────
sen26_rows.sort(key=lambda r: (
    0 if r["seeking_reelection"] else 1,
    -(r["years_served"] or 0)
))

sen26_df = pd.DataFrame(sen26_rows)

print(f"\n  → {len(sen26_df)} Class II Senate incumbents built (CSV write deferred until after Part 5)")

# ── Sanity checks ──────────────────────────────────────────────────────────────
print(f"\n── Sanity check: seeking re-election ──")
seeking_df  = sen26_df[sen26_df["seeking_reelection"] == True]
retiring_df = sen26_df[sen26_df["seeking_reelection"] == False]
print(f"  Seeking re-election:  {len(seeking_df)}")
print(f"  Not seeking:          {len(retiring_df)}")

print(f"\n── Sanity check: generations (seeking re-election only) ──")
for gen, grp in seeking_df.groupby("generation"):
    names = ", ".join(grp["last"].tolist())
    print(f"  {gen}: {names}")

print(f"\n── Sanity check: oldest seeking re-election ──")
if len(seeking_df) == 0:
    print("  ⚠ No seekers found — FEC data may be unavailable")
else:
    oldest = seeking_df.dropna(subset=["born"]).sort_values("born").iloc[0]
    print(f"  {oldest['first']} {oldest['last']} ({oldest['state']}) — born {int(oldest['born'])}, age end of next term: {int(oldest['age_end_next_term'])}")

print(f"\n── Sanity check: longest serving seeking re-election ──")
if len(seeking_df) == 0:
    print("  ⚠ No seekers found — FEC data may be unavailable")
else:
    longest = seeking_df.dropna(subset=["years_served"]).sort_values("years_served", ascending=False).iloc[0]
    print(f"  {longest['first']} {longest['last']} ({longest['state']}) — in Senate since {int(longest['since'])}, {int(longest['years_served'])} years")



# ══════════════════════════════════════════════════════════════════════════════
# PART 5: 2026 HOUSE ELECTIONS — CALCIFICATION WALL (House tab)
#
# Pulls all current House members from the `curr` JSON downloaded in Part 1.
# Every House seat is up in 2026. Re-election status is determined using a
# hardcoded list of confirmed retirements (same pattern as Senate Part 4).
#
# WHY NOT FEC API: The FEC incumbent_challenge=I query requires members to have
# formally filed paperwork — early in the cycle most haven't. Retirement
# announcements are national news and finite; it's easier to maintain a list
# of the ~40 people NOT running than to wait for 400+ people to file.
#
# HOW TO MAINTAIN: When a new retirement is announced, add their (state, district)
# tuple and a dated comment. To verify the list is complete, check:
#   https://ballotpedia.org/List_of_U.S._House_incumbents_who_are_not_running_for_re-election_in_2026
#
# The CSV output is capped at HOUSE_WALL_CAP bars total (all retirees first,
# then the oldest seekers by birth year) to keep the chart readable.
#
# Rows are appended to the combined incumbents CSV (senators_2026.csv) with
# chamber="House" so index.html can filter by chamber tab.
# ══════════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("PART 5: 2026 House elections — Calcification Wall (House tab)")
print("=" * 60)

HOUSE_WALL_CAP = 65   # max bars shown in the House Calcification Wall chart

# ── Hardcoded House retirement list ──────────────────────────────────────────
# (state, district_zero_padded) tuples for members retiring from public office.
# Members running for Senate, governor, or other offices are NOT listed here —
# they are still on the 2026 ballot, just for a different seat.
#
# Last validated against Ballotpedia: 2026-03-03
# Source: https://ballotpedia.org/United_States_House_of_Representatives_elections,_2026
#   (see "Incumbents retiring from public office" table — 24 members as of 2026-03-03)
#
# To add a new retirement: append the (state, district) tuple with a dated comment.
# Total confirmed public-office retirees as of 2026-03-03: 15
# NOTE: Members running for Senate, governor, or other offices are NOT listed
# here — they are still on the 2026 ballot, just for a different seat.
# Only members leaving elected office entirely are marked as non-seekers.
#
# To add a new retirement: append the (state, district) tuple with a comment.
# To verify the list is complete, check:
#   https://ballotpedia.org/United_States_House_of_Representatives_elections,_2026
#   (see "Incumbents retiring from public office" table)
RETIRING_DISTRICTS = {
    # 24 members confirmed retiring from public office as of 2026-03-03
    # (13 Democrats, 11 Republicans)
    # Source: ballotpedia.org — "Incumbents retiring from public office" table
    ("NV", "02"),   # Mark Amodei           R  — announced Feb 6, 2026
    ("GA", "11"),   # Barry Loudermilk      R  — announced Feb 4, 2026
    ("FL", "16"),   # Vern Buchanan         R  — announced Jan 27, 2026
    ("FL", "02"),   # Neal Dunn             R  — announced Jan 13, 2026
    ("CA", "26"),   # Julia Brownley        D  — announced Jan 8, 2026
    ("MD", "05"),   # Steny Hoyer           D  — announced Jan 7, 2026
    ("NY", "21"),   # Elise Stefanik        R  — announced Dec 19, 2025 (appointed Amb.)
    ("WA", "04"),   # Dan Newhouse          R  — announced Dec 17, 2025
    ("TX", "33"),   # Marc Veasey           D  — announced Dec 15, 2025
    ("TX", "37"),   # Lloyd Doggett         D  — announced Dec 5, 2025
    ("TX", "22"),   # Troy Nehls            R  — announced Nov 29, 2025
    ("NY", "07"),   # Nydia Velazquez       D  — announced Nov 20, 2025
    ("TX", "19"),   # Jodey Arrington       R  — announced Nov 11, 2025
    ("NJ", "12"),   # Bonnie Watson Coleman D  — announced Nov 10, 2025
    ("CA", "11"),   # Nancy Pelosi          D  — announced Nov 6, 2025
    ("IL", "04"),   # Jesus Garcia          D  — announced Nov 5, 2025
    ("ME", "02"),   # Jared Golden          D  — announced Nov 5, 2025
    ("TX", "10"),   # Michael McCaul        R  — announced Sep 14, 2025
    ("TX", "08"),   # Morgan Luttrell       R  — announced Sep 11, 2025
    ("NY", "12"),   # Jerrold Nadler        D  — announced Sep 1, 2025
    ("IL", "07"),   # Danny K. Davis        D  — announced Jul 31, 2025
    ("NE", "02"),   # Don Bacon             R  — announced Jun 30, 2025
    ("PA", "03"),   # Dwight Evans          D  — announced Jun 30, 2025
    ("IL", "09"),   # Jan Schakowsky        D  — announced May 5, 2025
}
print(f"  → {len(RETIRING_DISTRICTS)} confirmed House retirees (from public office)")

# ── Helper: first House term start year ───────────────────────────────────────
def first_house_year(leg):
    years = []
    for term in leg.get("terms", []):
        if term.get("type") == "rep":
            s = term.get("start", "")
            if s:
                try:
                    years.append(int(s[:4]))
                except:
                    pass
    return min(years) if years else None

# ── Build House incumbent rows ─────────────────────────────────────────────────
house26_rows = []

for leg in curr:
    terms = leg.get("terms", [])

    # Must have at least one House (rep) term
    if not any(t.get("type") == "rep" for t in terms):
        continue

    # Find most recent House term
    most_recent_rep = None
    for term in reversed(terms):
        if term.get("type") == "rep":
            most_recent_rep = term
            break
    if not most_recent_rep:
        continue

    # Keep only members whose current term ends Jan 2027 (119th Congress)
    # OR whose end date is not yet populated (some current members).
    end = most_recent_rep.get("end", "")
    if end and not end.startswith("2027-01"):
        continue   # term already expired or not 119th Congress

    bio   = leg.get("bio", {})
    name  = leg.get("name", {})
    last  = name.get("last", "")
    first = name.get("first", "")
    dob   = bio.get("birthday", "")
    by    = parse_birth_year(dob)
    gen   = classify_generation(by)

    state    = most_recent_rep.get("state", "")
    # district in JSON can be an int or string like "1", "12", "0" (at-large)
    raw_dist = most_recent_rep.get("district", "")
    district = str(int(raw_dist)).zfill(2) if str(raw_dist).isdigit() else str(raw_dist).zfill(2)
    party    = most_recent_rep.get("party", get_party(leg))
    since    = first_house_year(leg)

    seeking = (state, district) not in RETIRING_DISTRICTS

    # Years served as of Jan 2027 (end of current 119th Congress term)
    years_served  = (2027 - since)  if since else None
    age_now       = (2026 - by)     if by else None
    age_end_term  = (2029 - by)     if by else None   # end of next 2-year term

    house26_rows.append({
        "last":               last,
        "first":              first,
        "state":              state,
        "district":           district,
        "party":              party,
        "born":               by,
        "generation":         gen,
        "since":              since,
        "years_served":       years_served,
        "seeking_reelection": seeking,
        "age_now":            age_now,
        "age_end_next_term":  age_end_term,
        "chamber":            "House",
    })

print(f"\n  → {len(house26_rows)} current House members found")

# ── Cap to HOUSE_WALL_CAP bars: all retirees + oldest seekers ─────────────────
# This keeps the chart readable. All confirmed retirees are always included;
# remaining slots are filled by the oldest seekers (lowest birth year).
retirees = [r for r in house26_rows if not r["seeking_reelection"]]
seekers  = [r for r in house26_rows if  r["seeking_reelection"]]

# Sort seekers oldest-first (by birth year ascending = oldest first)
seekers.sort(key=lambda r: (r["born"] or 9999))

remaining_slots = max(0, HOUSE_WALL_CAP - len(retirees))
seekers_capped  = seekers[:remaining_slots]

print(f"  → Retirees included: {len(retirees)}")
print(f"  → Oldest seekers included: {len(seekers_capped)} of {len(seekers)} "
      f"(cap={HOUSE_WALL_CAP}, {len(seekers) - len(seekers_capped)} omitted)")

# Final list: retirees first (sorted by age desc), then oldest seekers (age desc)
retirees.sort(key=lambda r: (r["born"] or 9999))          # oldest retiree first
seekers_capped.sort(key=lambda r: (r["born"] or 9999))    # oldest seeker first
house26_capped = retirees + seekers_capped

house26_df = pd.DataFrame(house26_capped)
print(f"  → Final House rows for CSV: {len(house26_df)}")

# ── Combine Senate + House and write single CSV ───────────────────────────────
combined26_df = pd.concat([sen26_df, house26_df], ignore_index=True)
combined26_df.to_csv(os.path.join(DATA_DIR, "senators_2026.csv"), index=False)

print(f"\n✅ data/senators_2026.csv  — {len(combined26_df)} rows "
      f"({len(sen26_df)} Senate · {len(house26_df)} House)")

# ── Sanity checks ──────────────────────────────────────────────────────────────
print(f"\n── Senate sanity check: re-election status ──")
seeking_sen  = sen26_df[sen26_df["seeking_reelection"] == True]
retiring_sen = sen26_df[sen26_df["seeking_reelection"] == False]
print(f"  Seeking re-election:  {len(seeking_sen)}")
print(f"  Not seeking:          {len(retiring_sen)}")

if len(seeking_sen) > 0:
    boomers_plus = seeking_sen[seeking_sen["born"] <= 1960]
    print(f"  Boomers or older seeking: {len(boomers_plus)}")
    oldest_s = seeking_sen.dropna(subset=["born"]).sort_values("born").iloc[0]
    print(f"  Oldest seeking: {oldest_s['first']} {oldest_s['last']} ({oldest_s['state']}) "
          f"— age at end of next term: {int(oldest_s['age_end_next_term'])}")
    longest_s = seeking_sen.dropna(subset=["years_served"]).sort_values("years_served", ascending=False).iloc[0]
    print(f"  Longest-serving seeking: {longest_s['first']} {longest_s['last']} ({longest_s['state']}) "
          f"— {int(longest_s['years_served'])} yrs (since {int(longest_s['since'])})")
else:
    print("  ⚠ No Senate seekers found — FEC data may be unavailable")

print(f"\n── Senate generations (seeking only) ──")
for gen, grp in seeking_sen.groupby("generation"):
    names = ", ".join(grp["last"].tolist())
    print(f"  {gen}: {names}")

print(f"\n── House sanity check: re-election status ──")
seeking_hou  = house26_df[house26_df["seeking_reelection"] == True]
retiring_hou = house26_df[house26_df["seeking_reelection"] == False]
print(f"  Seeking re-election:  {len(seeking_hou)}")
print(f"  Not seeking:          {len(retiring_hou)}")

if len(seeking_hou) > 0:
    oldest_h  = seeking_hou.dropna(subset=["born"]).sort_values("born").iloc[0]
    longest_h = seeking_hou.dropna(subset=["years_served"]).sort_values("years_served", ascending=False).iloc[0]
    print(f"  Oldest seeking: {oldest_h['first']} {oldest_h['last']} ({oldest_h['state']}-{oldest_h['district']}) "
          f"— age at end of next term: {int(oldest_h['age_end_next_term'])}")
    print(f"  Longest-serving seeking: {longest_h['first']} {longest_h['last']} ({longest_h['state']}-{longest_h['district']}) "
          f"— {int(longest_h['years_served'])} yrs (since {int(longest_h['since'])})")
else:
    print("  ⚠ No House seekers found — FEC data may be unavailable")

print(f"\n── House top-10 longest-serving (seeking re-election) ──")
if len(seeking_hou) > 0:
    top10 = seeking_hou.dropna(subset=["years_served"]).sort_values("years_served", ascending=False).head(10)
    for _, r in top10.iterrows():
        print(f"  {r['first']} {r['last']} ({r['state']}-{r['district']}) — {int(r['years_served'])} yrs — {r['generation']}")

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("ALL DONE")
print(f"  data/congress_historical.csv       — {len(hist_df)} congress rows")
print(f"  data/congress_snapshots_detail.csv — {len(snap_df)} snapshot rows")
print(f"  data/bls_gen_comparison.csv        — {len(bls_df)} sector rows")
print(f"  data/presidents.csv                — {len(pres_df)} term rows")
print(f"  data/senators_2026.csv             — {len(combined26_df)} rows "
      f"({len(sen26_df)} Senate · {len(house26_df)} House)")
print("=" * 60)

print("\n── Sanity check: mean age ──")
print(f"  {int(hist_df.iloc[0]['year'])} → {hist_df.iloc[0]['mean_age']}  (expected ~48.3)")
print(f"  {int(hist_df.iloc[-1]['year'])} → {hist_df.iloc[-1]['mean_age']}  (expected ~58.5)")

