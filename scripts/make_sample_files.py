"""Write the small test files for the file types phase into data/raw (not committed).

Run:  .venv\\Scripts\\python scripts\\make_sample_files.py

Their text is copied from the public US government PDFs in PLAN.md (Data section), so
eval/filetype_questions.csv can check exact answers. No AI, no internet.
"""

import csv
from pathlib import Path

DATA_DIR = Path("data/raw")

TXT = """Certificate of Number

When a vessel is moved to a new state of principal use, the CON remains valid for 60 days.

If the CON becomes invalid for any reason, it must be surrendered to the issuing authority
within 15 days.

Cold shock will pass in about one minute.

Boat owners are responsible for keeping their vessel's ventilation systems in operating condition.
"""

MD = """# Echo Soundings

Most types of echo sounders are factory calibrated for a velocity of sound in water
of 800 fathoms per second.

## Small craft

Large vessels may appear to move slowly due to their large size but actually transit at speeds
in excess of 12 knots.

## Distances

A statute mile is 5,280 feet or about 0.87 nautical mile.
"""

CSV_ROWS = [
    ["Vessel length", "Light", "Minimum range"],
    ["50 meters or more", "masthead light", "6 miles"],
    ["50 meters or more", "sidelight", "3 miles"],
    ["less than 12 meters", "towing light", "2 miles"],
    ["less than 50 meters", "all-round light", "3 miles"],
]

HTML = """<!doctype html>
<html><head><title>Stairways</title><style>p { color: red; }</style></head>
<body>
<script>var hidden = "The script says 99 feet.";</script>
<h1>Handrails</h1>
<p>Temporary handrails must have a minimum clearance of 3 inches (8 cm) between the handrail and walls.</p>
<h1>Cages for Fixed Ladders</h1>
<p>Horizontal bands must be spaced at intervals not more than 4 feet (1.2 m) apart measured from centerline to centerline.</p>
<ul><li>Insides of cages must be clear of projections.</li></ul>
<h1>Stairways</h1>
<p>Variations in riser height or stair tread depth must not exceed 1/4 inch in any stairway system.</p>
</body></html>
"""


def write_group_1():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "sample_boating.txt").write_text(TXT, encoding="utf-8")
    (DATA_DIR / "sample_navigation.md").write_text(MD, encoding="utf-8")
    with open(DATA_DIR / "sample_lights.csv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(CSV_ROWS)
    (DATA_DIR / "sample_stairs.html").write_text(HTML, encoding="utf-8")


def write_group_2():
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation

    doc = Document()
    doc.add_heading("Locks", level=1)
    doc.add_paragraph("Tie your craft to the mooring devices after entering; a minimum of 50 feet of line is recommended.")
    doc.add_heading("Termination of Use", level=1)
    doc.add_paragraph("Violators may be fined up to $1,000, or imprisoned for up to one year, or both.")
    doc.add_heading("Naval Vessel Protection Zone", level=1)
    doc.add_paragraph("Violations of the Naval Vessel Protection Zone are a felony offense punishable by up to 6 years "
                      "in prison and/or up to $250,000 in fines.")
    doc.save(DATA_DIR / "sample_locks.docx")

    deck = Presentation()
    slides = [("Fire Extinguishers", "The extinguisher is not expired (for non-rechargeable extinguishers, 12 years from date stamped on bottom)."),
              ("Pyrotechnic Devices", "Check the expiration date (42 months after the date of manufacture)."),
              ("Life Jackets", "Any boat 16 feet and longer (except canoes and kayaks) must also carry one throwable PFD (Type IV).")]
    for title, body in slides:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    deck.save(DATA_DIR / "sample_safety.pptx")

    book = Workbook()
    sheet = book.active
    sheet.title = "Sound signals"
    for row in [("Signal", "Meaning"), ("One short blast", "I am altering my course to starboard"),
                ("Two short blasts", "I am altering my course to port"), ("Three short blasts", "I am operating astern propulsion")]:
        sheet.append(row)
    stairs = book.create_sheet("Stairways")
    for row in [("Item", "Limit"), ("Landing depth", "at least 30 inches"), ("Stair rail load", "at least 200 pounds")]:
        stairs.append(row)
    book.save(DATA_DIR / "sample_signals.xlsx")


def main():
    write_group_1()
    write_group_2()
    print("Sample files written to data/raw.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
