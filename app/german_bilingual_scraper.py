"""Manitoba German Language Arts (Bilingual) K-S4 scraper.

Parses the K-S4 German Language Arts: Manitoba Curriculum Framework of Outcomes (2003).
7 GLOs across 13 grades (K, 1-8, S1-S4), ~1200 total SLOs.

Uses fitz rect-based column extraction to handle multi-column layout
(4 columns for K-3, 3 columns for 4-6, 7-S1, S2-S4).

Source: edu.gov.mb.ca/k12/cur/languages/german/framework_ks4/ks4framework.pdf
"""

import json
import logging
import re
from pathlib import Path

import fitz
import httpx

logger = logging.getLogger(__name__)

PDF_URL = "https://www.edu.gov.mb.ca/k12/cur/languages/german/framework_ks4/ks4framework.pdf"

ALL_GRADES = [
    "Kindergarten", "Grade 1", "Grade 2", "Grade 3",
    "Grade 4", "Grade 5", "Grade 6",
    "Grade 7", "Grade 8", "Senior 1",
    "Senior 2", "Senior 3", "Senior 4",
]

GRADE_MAP = {
    "Kindergarten": "K", "Grade 1": "1", "Grade 2": "2", "Grade 3": "3",
    "Grade 4": "4", "Grade 5": "5", "Grade 6": "6", "Grade 7": "7",
    "Grade 8": "8", "Senior 1": "S1", "Senior 2": "S2",
    "Senior 3": "S3", "Senior 4": "S4",
}

GLO_DESCRIPTIONS = {
    "1": "Explore thoughts, ideas, feelings, and experiences.",
    "2": "Comprehend and respond personally and critically to literary and media texts.",
    "3": "Manage ideas and information.",
    "4": "Enhance the clarity and artistry of communication.",
    "5": "Celebrate and build community.",
    "6": "Specific Language Component: Apply knowledge of German language to express meaning.",
    "7": "Culture: Explore, understand, and appreciate German language culture.",
}


def _download_pdf(url: str) -> bytes:
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def _assign_column(x: float, grade_x_sorted: list[tuple[str, float]]) -> str:
    """Assign an x-position to the nearest grade column using midpoints."""
    for i in range(len(grade_x_sorted)):
        if i == len(grade_x_sorted) - 1:
            return grade_x_sorted[i][0]
        midpoint = (grade_x_sorted[i][1] + grade_x_sorted[i + 1][1]) / 2
        if x < midpoint:
            return grade_x_sorted[i][0]
    return grade_x_sorted[-1][0]


def _parse_pdf(doc: fitz.Document) -> dict[str, list[dict]]:
    """Extract SLOs from the multi-column PDF layout."""
    all_slos: dict[str, list[dict]] = {}
    page_width = doc[20].rect.width

    for p in range(20, 124):
        if p >= len(doc):
            break
        page = doc[p]
        blocks = page.get_text("dict")["blocks"]

        # Find grade header positions
        grade_x = []
        for b in blocks:
            if "lines" not in b:
                continue
            for line in b["lines"]:
                text = "".join(s["text"] for s in line["spans"]).strip()
                if text in ALL_GRADES:
                    grade_x.append((text, line["bbox"][0]))

        if not grade_x:
            continue
        grade_x.sort(key=lambda g: g[1])

        # Detect GLO number
        full_text = page.get_text()
        glo_match = re.search(r"General Learning Outcome (\d+)", full_text)
        if not glo_match:
            continue
        glo_num = glo_match.group(1)

        # Find cluster name from page header area
        cluster_name = ""
        for b in blocks:
            if "lines" not in b:
                continue
            for line in b["lines"]:
                text = "".join(s["text"] for s in line["spans"]).strip()
                y = line["bbox"][1]
                if y < 180 and text and len(text) > 5:
                    if (
                        not text.startswith("German Language")
                        and not re.match(r"^\d+ /", text)
                        and "General Learning" not in text
                        and text not in ALL_GRADES
                        and "By the end" not in text
                    ):
                        cluster_name = text
                        break
            if cluster_name:
                break

        # Build column rects using midpoints between grade headers
        col_rects = []
        for i, (g, gx) in enumerate(grade_x):
            left = gx - 50 if i == 0 else (grade_x[i - 1][1] + gx) / 2
            right = page_width - 20 if i == len(grade_x) - 1 else (gx + grade_x[i + 1][1]) / 2
            col_rects.append((g, left, right))

        # Extract SLOs per column
        for grade_label, left, right in col_rects:
            grade_key = GRADE_MAP.get(grade_label, grade_label)
            rect = fitz.Rect(left, 220, right, 700)
            col_text = page.get_text("text", clip=rect)

            if not col_text.strip():
                continue

            lines = col_text.split("\n")
            current_slo = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                slo_match = re.match(r"^(\d+)\.\s*(.*)", line)
                if slo_match:
                    if current_slo:
                        all_slos.setdefault(grade_key, []).append(current_slo)

                    slo_num = slo_match.group(1)
                    desc = slo_match.group(2).strip()

                    current_slo = {
                        "code": f"GER.{grade_key}.{glo_num}.{slo_num}",
                        "glo": f"GLO {glo_num}",
                        "glo_description": GLO_DESCRIPTIONS.get(glo_num, ""),
                        "cluster": cluster_name,
                        "description": desc,
                    }
                elif current_slo and line not in ALL_GRADES:
                    if any(
                        line.startswith(s)
                        for s in ("__", "*Refer", "By the end")
                    ) or "General Learning" in line or "Students will" in line:
                        continue
                    current_slo["description"] += " " + line

            if current_slo:
                all_slos.setdefault(grade_key, []).append(current_slo)

    return all_slos


def scrape_all_german_bilingual(
    output_dir: Path,
    progress_callback=None,
) -> dict[str, list]:
    """Scrape German Language Arts (Bilingual) K-S4 outcomes."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback("Downloading German K-S4 Bilingual PDF...")

    pdf_bytes = _download_pdf(PDF_URL)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if progress_callback:
        progress_callback(f"Parsing {doc.page_count} pages...")

    all_slos = _parse_pdf(doc)
    doc.close()

    results: dict[str, list] = {}
    grade_order = ["K"] + [str(i) for i in range(1, 9)] + ["S1", "S2", "S3", "S4"]

    for i, grade_key in enumerate(grade_order, 1):
        slos = all_slos.get(grade_key, [])
        grade_label = f"Kindergarten" if grade_key == "K" else f"Grade {grade_key}"
        if progress_callback:
            progress_callback(f"[{i}/13] German Bilingual {grade_label}: {len(slos)} SLOs")

        # Group by GLO for cluster structure
        glo_groups: dict[str, list[dict]] = {}
        for slo in slos:
            glo_groups.setdefault(slo["glo"], []).append(slo)

        clusters = []
        for glo_name, glo_slos in glo_groups.items():
            # Sub-group by cluster within each GLO
            cluster_groups: dict[str, list[dict]] = {}
            for s in glo_slos:
                cluster_groups.setdefault(s["cluster"], []).append(s)

            for cluster_title, cluster_slos in cluster_groups.items():
                clusters.append({
                    "id": f"{glo_name}_{cluster_title}",
                    "title": f"{glo_name}: {cluster_title}",
                    "description": GLO_DESCRIPTIONS.get(glo_name.replace("GLO ", ""), ""),
                    "specific_learning_outcomes": cluster_slos,
                })

        output_data = {
            "subject": "German Language Arts (Bilingual)",
            "grade": grade_key,
            "course": f"German Language Arts (Bilingual) {grade_label}",
            "framework_year": "Framework 2003",
            "clusters": clusters,
        }

        filename = f"GermanBilingual_{grade_key}.json"
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        results[filename] = slos
        if progress_callback:
            progress_callback(f"  → {filename}: {len(slos)} outcomes")

    total = sum(len(v) for v in results.values())
    if progress_callback:
        progress_callback(f"\nGerman Bilingual K-S4: {total} outcomes across {len(results)} grades")

    return results
