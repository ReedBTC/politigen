# Politigen — Generational Representation in the U.S. Government

A data visualization project tracking how generations have risen, dominated, and been displaced across 125 years of U.S. legislative history (57th–119th Congress, 1901–2025).

![Politigen](https://img.shields.io/badge/Congress-57th–119th-e8875a?style=flat-square) ![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square) ![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

---

## What It Shows

**Section 00 — Who Actually Runs America?**
Compares the generational makeup of elected officials against every BLS workforce sector. Millennials and Gen Z make up ~60% of workers but barely register in Congress.

**Section 01 — The Rise & Fall of Generations**
Interactive line charts of each generation's share of the House and Senate from 1901 to 2025. Presidential term dots sit on each president's generation curve. Boomers have held power longer than any generation before them — and still aren't letting go.

**Section 02 — Congress Is Getting Older**
Mean age of the Senate and House since 1901, with presidential ages overlaid. A dramatic aging trend began in the 1980s and has never reversed.

**Section 03 — Aging In Place**
Snapshot cards at four moments in history (1965, 1985, 2005, 2025) showing each generation's seat share and mean age. Toggle between House and Senate views.

**Section 04 — The Calcification Wall**
Every Class II senator on the 2026 ballot, visualized as a pillar. Height = years in the Senate. Color = generation. Seekers glow; retirees fade. Sort by tenure, age, or state. Stat callouts show how many of the re-election seekers are Boomer-or-older and what age the oldest would reach at the end of a next full term.

---

## Quick Start

```bash
# Clone the repo
git clone https://github.com/ReedBTC/politigen.git
cd politigen

# Install dependencies
pip install -r requirements.txt

# (Optional) Refresh data — CSVs are already committed
python collect_politigen.py

# View the site locally via any static server, e.g.:
python -m http.server 8000
# then open http://localhost:8000
# (opening index.html as a file:// URL won't work — fetch() is blocked by browsers)
```

---

## Repository Structure

```
politigen/
├── index.html                        # The full visualization (self-contained)
├── collect_politigen.py              # Data collection script
├── requirements.txt
├── .gitignore
└── data/
    ├── congress_historical.csv       # One row per Congress, 57th–119th (1901–2025)
    ├── congress_snapshots_detail.csv # Per-generation stats at 1965, 1985, 2005, 2025
    ├── bls_gen_comparison.csv        # Generational share by BLS industry sector
    ├── presidents.csv                # One row per presidential term start since 1901
    └── senators_2026.csv             # Class II Senate + all House incumbents on the 2026 ballot
```

---

## Data Sources

| Source | What It Provides |
|--------|-----------------|
| [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators) | Every Congress member since 1789 with exact birth dates and term dates |
| [BLS CPS Table 18b](https://www.bls.gov/cps/cpsaat18b.xlsx) | Employed persons by industry and age bracket (annual average) |
| [FEC Candidates API](https://api.open.fec.gov/developers) | 2026 House incumbent filings (`incumbent_challenge=I`), used to determine which House members are seeking re-election |
| [Ballotpedia](https://ballotpedia.org/United_States_Senate_elections,_2026) | Incumbents retiring from public office - hardcoded, needs to be manually updated in the python script |

Generational assignments use **Strauss-Howe** cutoffs:

| Generation | Birth Years |
|------------|-------------|
| Pre-G.I. (fallback) | before 1843 |
| Progressive | 1843–1859 |
| Missionary | 1860–1882 |
| Lost | 1883–1900 |
| G.I. Generation | 1901–1924 |
| Silent | 1925–1942 |
| Baby Boom | 1943–1960 |
| Gen X (13ers) | 1961–1981 |
| Millennial | 1982–2005 |
| Gen Z | 2006+ |

Congressional data uses exact birth dates from the legislators JSON. BLS data uses age brackets, so generational shares are approximated by proportionally splitting BLS's 10-year brackets across generation boundaries.

---

## Refreshing the Data

Running `collect_politigen.py` fetches fresh data from GitHub, BLS, and the FEC and overwrites all five CSVs. The CSVs are committed to the repo so the site works out of the box without running the script.

```bash
python collect_politigen.py
```

Expected output:
```
✅ data/congress_historical.csv        — 63 rows
✅ data/congress_snapshots_detail.csv  — 31 rows
✅ data/bls_gen_comparison.csv         — 15 rows
✅ data/presidents.csv                 — 36 rows
✅ data/senators_2026.csv              — ~470 rows (33 Senate + ~435 House)
```

---

## Keeping `senators_2026.csv` Current

The re-election status for Senate and House incumbents is determined two different ways, for good reason:

**House — FEC API (automatic).** With 435 seats, it's impractical to track individual retirement announcements. The script queries the FEC Candidates API for House incumbents who have filed for 2026 (`office=H, incumbent_challenge=I`). House members tend to file relatively early in the cycle, so this signal is reliable. No manual maintenance needed.

**Senate — hardcoded retirement list (manual).** The FEC approach breaks down for Senate because senators file paperwork much later — early in a cycle, only 1–2 of 33 incumbents may have filed, which would incorrectly mark the other 31 as "not seeking re-election." Instead, the script defaults everyone to `seeking=True` and maintains a small `RETIRING_STATES` set of confirmed retirements. Since there are only ever ~8 retirements per cycle and each one is national news, this is easy to keep up to date.

**To add a new Senate retirement:** open `collect_politigen.py`, find the `RETIRING_STATES` set near the top of Part 4, add the two-letter state code with a dated comment, update the "Last validated" date, and rerun the script. Example:

```python
RETIRING_STATES = {
    "KY",   # Mitch McConnell   -- announced Feb 20, 2025
    "WY",   # Cynthia Lummis    -- announced Dec 19, 2025
    ...
}
```

To verify the list is complete, check:
[ballotpedia.org/List_of_U.S._Senate_incumbents_who_are_not_running_for_re-election_in_2026](https://ballotpedia.org/List_of_U.S._Senate_incumbents_who_are_not_running_for_re-election_in_2026)

---

## Tech Stack

- **Python** — data collection and processing (`requests`, `pandas`, `openpyxl`)
- **HTML / CSS / JavaScript** — visualization (no frameworks, pure SVG)
- **Fonts** — Bebas Neue, DM Mono, DM Sans (Google Fonts)
