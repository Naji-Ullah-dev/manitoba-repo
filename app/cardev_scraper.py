"""Manitoba Career Development curriculum scraper (Grades 9-12).

Parses full-credit Foundation for Implementation PDFs to extract:
  - Units with descriptions
  - GLOs with SLOs grouped hierarchically
  - Appendices metadata

Output format:
  units → glos → slos  (one JSON per grade)

Source: edu.gov.mb.ca/k12/cur/cardev/gr{N}_found/docs/full_doc.pdf
"""

import json
import logging
import re
from pathlib import Path

import fitz
import httpx

logger = logging.getLogger(__name__)

GRADE_INFO: dict[str, dict] = {
    "9": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/cardev/gr9_found/docs/full_doc.pdf",
        "subtitle": "Life/Work Exploration",
    },
    "10": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/cardev/gr10_found/docs/full_doc.pdf",
        "subtitle": "Life/Work Planning",
    },
    "11": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/cardev/gr11_found/docs/full_doc.pdf",
        "subtitle": "Life/Work Building",
    },
    "12": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/cardev/gr12_found/docs/full_doc.pdf",
        "subtitle": "Life/Work Transitioning",
    },
}

GLO_TITLES: dict[str, str] = {
    "A": "Build and maintain a positive self-image.",
    "B": "Interact positively and effectively with others.",
    "C": "Change and grow throughout life.",
    "D": "Locate and effectively use life/work information.",
    "E": "Understand the relationship between work and society/economy.",
    "F": "Maintain balanced life and work roles.",
    "G": "Understand the changing nature of life/work roles.",
    "H": "Participate in lifelong learning supportive of life/work goals.",
    "I": "Make life/work enhancing decisions.",
    "J": "Understand, engage in, and manage own life/work building process.",
    "K": "Secure/create and maintain work.",
}

APPENDICES = [
    {
        "id": "A",
        "title": "Blackline Masters: Units 1\u20135",
        "short_description": "Reproducible blackline masters supporting the learning experiences across Units 1 to 5.",
    },
    {
        "id": "B",
        "title": "Strategies for Instruction and Assessment",
        "short_description": "Instructional and assessment strategies referenced throughout the units.",
    },
]


def _download(url: str, dest: Path):
    if dest.exists() and dest.stat().st_size > 10000:
        return
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def _parse_foundation_pdf(doc) -> list[dict]:
    """Parse the Foundation PDF intro section to extract units, GLOs, and SLOs."""
    units: list[dict] = []

    current_unit_num = None
    current_unit_title = ""
    current_unit_desc_parts: list[str] = []
    capturing_desc = False

    current_glo_code = ""
    current_slos: list[dict] = []
    unit_glos: list[dict] = []

    slo_re = re.compile(r"^(\d+\.[A-Z]\.\d+)\s*(.*)")
    glo_re = re.compile(r"General Learning Outcome \(GLO\)\s+([A-Z]):")
    unit_re = re.compile(r"^Unit\s+(\d+):\s+(.+)")

    def _save_glo():
        nonlocal current_glo_code, current_slos
        if current_glo_code and current_slos:
            unit_glos.append({
                "code": current_glo_code,
                "title": GLO_TITLES.get(current_glo_code, ""),
                "slos": current_slos,
            })
        current_slos = []
        current_glo_code = ""

    def _save_unit():
        nonlocal current_unit_num, current_unit_desc_parts, capturing_desc, unit_glos
        _save_glo()
        if current_unit_num:
            desc = re.sub(r"\s+", " ", " ".join(current_unit_desc_parts)).strip()
            units.append({
                "id": f" Unit {current_unit_num}",
                "title": current_unit_title,
                "description": desc,
                "glos": unit_glos,
            })
        current_unit_desc_parts = []
        capturing_desc = False
        unit_glos = []

    # Scan intro pages (typically pages 10-35) for unit definitions
    for pg_idx in range(10, min(45, doc.page_count)):
        text = doc[pg_idx].get_text()
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            l = lines[i].strip()
            i += 1

            if not l:
                continue
            # Skip spaced headers and page numbers
            if re.match(r"^[A-Z]\s[a-z]\s[a-z]", l):
                continue
            if re.match(r"^\d+$", l):
                continue
            if l.startswith("Specific Learning Outcome") or l.startswith("Students will be able"):
                capturing_desc = False
                continue

            # Unit header
            um = unit_re.match(l)
            if um:
                _save_unit()
                current_unit_num = um.group(1)
                current_unit_title = um.group(2)
                current_unit_desc_parts = []
                capturing_desc = True
                continue

            # GLO header
            gm = glo_re.match(l)
            if gm:
                _save_glo()
                if capturing_desc and current_unit_desc_parts:
                    capturing_desc = False
                current_glo_code = gm.group(1)
                continue

            # SLO code
            sm = slo_re.match(l)
            if sm:
                capturing_desc = False
                code = sm.group(1)
                desc_parts = [sm.group(2).strip()] if sm.group(2).strip() else []
                # Collect continuation lines
                while i < len(lines):
                    nl = lines[i].strip()
                    if not nl:
                        i += 1
                        continue
                    if slo_re.match(nl) or glo_re.match(nl) or unit_re.match(nl):
                        break
                    if nl.startswith("General Learning") or nl.startswith("Specific Learning") or nl.startswith("Students will be able"):
                        break
                    if re.match(r"^[A-Z]\s[a-z]\s[a-z]", nl) or re.match(r"^\d+$", nl):
                        break
                    desc_parts.append(nl)
                    i += 1
                desc = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()
                current_slos.append({"code": code, "description": desc})
                continue

            # Unit description continuation
            if capturing_desc and current_unit_num:
                current_unit_desc_parts.append(l)

    # Save last unit
    _save_unit()

    # Deduplicate: keep only units that have GLOs with SLOs
    seen_unit_nums: set[str] = set()
    deduped: list[dict] = []
    for u in units:
        num = u["id"].strip().replace("Unit ", "")
        has_slos = any(len(g["slos"]) > 0 for g in u["glos"])
        if has_slos and num not in seen_unit_nums:
            seen_unit_nums.add(num)
            deduped.append(u)

    return deduped


def scrape_all_cardev(
    output_dir: Path,
    progress_callback=None,
) -> dict[str, list]:
    """Scrape Career Development Grades 9-12 from Foundation PDFs."""
    results: dict[str, list] = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path("/tmp/cardev_found_pdfs")
    tmp_dir.mkdir(exist_ok=True)

    for grade, info in GRADE_INFO.items():
        url = info["url"]
        subtitle = info["subtitle"]

        if progress_callback:
            progress_callback(f"Downloading Career Dev Grade {grade} Foundation PDF...")

        try:
            pdf_path = tmp_dir / f"gr{grade}_found.pdf"
            _download(url, pdf_path)
        except Exception as e:
            if progress_callback:
                progress_callback(f"ERROR downloading Grade {grade}: {e}")
            continue

        if progress_callback:
            progress_callback(f"Parsing Career Dev Grade {grade}...")

        doc = fitz.open(str(pdf_path))
        units = _parse_foundation_pdf(doc)
        doc.close()

        output_data = {
            "subject": f"Career Development: {subtitle} 2017",
            "grade": grade,
            "framework_year": "2017",
            "document_title": (
                f"Grade {grade} Career Development: {subtitle}: "
                "Manitoba Curriculum Framework of Outcomes and A Foundation for Implementation"
            ),
            "units": units,
            "appendices": APPENDICES,
        }

        results[grade] = units

        filename = f"CareerDev_Grade_{grade}.json"
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)

        total_slos = sum(
            len(s) for u in units for g in u["glos"] for s in [g["slos"]]
        )
        if progress_callback:
            progress_callback(
                f"Saved {filename}: {len(units)} units, {total_slos} SLOs"
            )

    return results
