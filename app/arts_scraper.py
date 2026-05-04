"""Manitoba Arts Education curriculum scraper (K-8, all 4 disciplines).

Extracts the full recursive learning hierarchy from Dance, Dramatic Arts,
Music, and Visual Arts K-8 framework PDFs (2021, Second Edition).

Output per discipline: one comprehensive JSON with
  subject → learning_areas → recursive_learnings → enacted_learnings

Learning Areas: Making (M), Creating (CR), Connecting (C), Responding (R)
Code format: {GradeBand} {Prefix}–{LA}{Num}[.{Sub}]
  e.g.: K–4 DA–M1.1, 5–8 DR–CR1.6, K M–M1.1
"""

import json
import logging
import re
from pathlib import Path

import fitz
import httpx

logger = logging.getLogger(__name__)

DISCIPLINES: dict[str, dict] = {
    "Dance": {
        "prefix": "DA",
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/dance_k8_2nd.pdf",
        "full_name": "Kindergarten to Grade 8 Dance: Manitoba Curriculum Framework, Second Edition",
    },
    "Dramatic Arts": {
        "prefix": "DR",
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/drama_k8_2nd.pdf",
        "full_name": "Kindergarten to Grade 8 Dramatic Arts: Manitoba Curriculum Framework, Second Edition",
    },
    "Music": {
        "prefix": "M",
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/music_k8_2nd.pdf",
        "full_name": "Kindergarten to Grade 8 Music: Manitoba Curriculum Framework, Second Edition",
    },
    "Visual Arts": {
        "prefix": "VA",
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/visual_k8_2nd.pdf",
        "full_name": "Kindergarten to Grade 8 Visual Arts: Manitoba Curriculum Framework, Second Edition",
    },
}

LA_INFO: dict[str, str] = {
    "M": "Making (M)",
    "CR": "Creating (CR)",
    "C": "Connecting (C)",
    "R": "Responding (R)",
}

_SPACED_HEADERS = [
    "R e c u r s i v e", "M a k i n g", "C r e a t i n g",
    "C o n n e c t i n g", "R e s p o n d i n g",
    "K i n d e r g a r t e n",
]


def _download(url: str, dest: Path) -> Path:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest


def _normalize_dash(text: str) -> str:
    return text.replace(" – ", "–").replace("– ", "–").replace(" –", "–")


def _get_col_idx(grade_band: str, n_cols: int, page_first_grade: int) -> int:
    """Map a grade band to its description column index on the current page."""
    gb = grade_band.replace("\u2013", "-").replace("–", "-")
    first_str = gb.split("-")[0]
    if first_str == "K":
        first_g = 0
    else:
        try:
            first_g = int(first_str)
        except ValueError:
            first_g = 0

    if first_g < page_first_grade:
        return 0

    idx = first_g - page_first_grade
    return min(idx, n_cols - 1)


def _parse_discipline(doc: fitz.Document, prefix: str) -> dict:
    """Parse one arts discipline PDF into the hierarchical structure."""

    code_re = re.compile(
        rf"^([\dK]+(?:[–\-]\d+)?)\s+"
        rf"{re.escape(prefix)}[–\-]([A-Z]+\d+(?:\.\d+)?)$"
    )

    # ── Appendices from TOC ──────────────────────────────────────────
    appendices: list[dict] = []
    for t in doc.get_toc():
        m = re.match(r"Appendix\s+([A-Z]):\s*(.*)", t[1])
        if m:
            appendices.append({"id": m.group(1), "title": m.group(2).strip()})

    # ── LA descriptions from overview pages ──────────────────────────
    la_descriptions: dict[str, str] = {}
    for p_idx in range(doc.page_count):
        text = doc[p_idx].get_text()
        if "RECURSIVE LEARNINGS" not in text:
            continue
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            clean = line.replace(" ", "")
            la_m = re.match(
                r"(Making|Creating|Connecting|Responding)\(([A-Z]+)\)", clean
            )
            if not la_m:
                continue
            la_code = la_m.group(2)
            parts: list[str] = []
            for j in range(i + 1, min(i + 5, len(lines))):
                nl = lines[j]
                if nl.startswith("RECURSIVE") or re.match(r"^[A-Z]{1,2}[–\-]", nl):
                    break
                if nl.startswith("The learner") or parts:
                    parts.append(nl)
            if parts:
                la_descriptions[la_code] = re.sub(r"\s+", " ", " ".join(parts)).strip()

    # ── Map pages → RL section ───────────────────────────────────────
    page_to_rl: dict[int, str] = {}
    for p_idx in range(doc.page_count):
        for block in doc[p_idx].get_text("dict")["blocks"]:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                st = " ".join(s["text"] for s in line["spans"]).strip()
                collapsed = re.sub(r"(?<=\w)\s(?=\w)", "", st)
                m = re.match(
                    rf"(?:Making|Creating|Connecting|Responding)\s*\(\s*"
                    rf"{re.escape(prefix)}\s*[–\-]\s*([A-Z]+\d+)\s*\)",
                    collapsed,
                )
                if m:
                    page_to_rl[p_idx] = f"{prefix}–{m.group(1)}"
                    break

    # ── RL titles ────────────────────────────────────────────────────
    rl_titles: dict[str, str] = {}
    for p_idx, rl_code in page_to_rl.items():
        if rl_code in rl_titles:
            continue
        lines = [l.strip() for l in doc[p_idx].get_text().split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if not line.startswith("The learner") or "is able to" in line:
                continue
            title = line
            for j in range(i + 1, min(i + 5, len(lines))):
                nl = lines[j]
                if nl.startswith("The learner is") or re.match(r"^(Grade|Kindergarten)", nl):
                    break
                if not nl or nl.startswith("*") or "RECURSIVE" in nl:
                    break
                if nl[0].islower() or nl.startswith(("of ", "and ", "in ")):
                    title += " " + nl
                else:
                    break
            rl_titles[rl_code] = re.sub(r"\s+", " ", title).strip().rstrip("*").strip()
            break

    # ── Enacted learnings (column-aware extraction) ──────────────────
    enacted_by_rl: dict[str, list[dict]] = {}

    for p_idx in range(doc.page_count):
        if p_idx not in page_to_rl:
            continue
        current_rl = page_to_rl[p_idx]
        enacted_by_rl.setdefault(current_rl, [])

        dict_blocks = doc[p_idx].get_text("dict")["blocks"]

        # Detect grade-column positions from header spans
        header_xs: list[float] = []
        page_first_grade = 0
        for block in dict_blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                t = " ".join(s["text"] for s in line["spans"]).strip()
                if not re.match(r"^(Kindergarten|Grade \d)", t):
                    continue
                for span in line["spans"]:
                    st = span["text"].strip()
                    gm = re.match(r"^Grade (\d)", st)
                    if gm:
                        header_xs.append(span["bbox"][0])
                        g = int(gm.group(1))
                        if not header_xs or span["bbox"][0] <= min(header_xs):
                            page_first_grade = g
                    elif st.startswith("Kindergarten"):
                        header_xs.append(span["bbox"][0])
                        page_first_grade = 0

        header_xs.sort()
        if not header_xs:
            header_xs = [70.0]
        if header_xs:
            first_hdr = header_xs[0]
            for block in dict_blocks:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        st = span["text"].strip()
                        if span["bbox"][0] == first_hdr:
                            if st.startswith("Kindergarten"):
                                page_first_grade = 0
                            else:
                                gm2 = re.match(r"^Grade (\d)", st)
                                if gm2:
                                    page_first_grade = int(gm2.group(1))

        # Column boundaries via midpoints
        col_bounds: list[tuple[float, float]] = []
        for ci in range(len(header_xs)):
            left = 0.0 if ci == 0 else (header_xs[ci - 1] + header_xs[ci]) / 2
            right = 800.0 if ci == len(header_xs) - 1 else (header_xs[ci] + header_xs[ci + 1]) / 2
            col_bounds.append((left, right))
        n_cols = len(col_bounds)

        # Collect line-level items
        line_items: list[dict] = []
        for block in dict_blocks:
            if "lines" not in block:
                continue
            for line in block["lines"]:
                t = " ".join(s["text"] for s in line["spans"]).strip()
                if t and len(t) > 2:
                    t = _normalize_dash(t)
                    bbox = line["bbox"]
                    line_items.append(
                        {"y": bbox[1], "x0": bbox[0], "x1": bbox[2], "text": t}
                    )
        line_items.sort(key=lambda x: (x["y"], x["x0"]))

        for i, item in enumerate(line_items):
            m = code_re.match(item["text"])
            if not m:
                continue

            grade_band = m.group(1)
            code_part = m.group(2)

            # Fix known PDF typo: Music "M–L3.15" → "M–M3.15"
            if prefix == "M" and code_part.startswith("L"):
                code_part = "M" + code_part[1:]

            full_code = f"{grade_band} {prefix}–{code_part}"

            col_idx = _get_col_idx(grade_band, n_cols, page_first_grade)
            if col_idx < n_cols:
                desc_x_min, desc_x_max = col_bounds[col_idx]
            else:
                desc_x_min, desc_x_max = 0.0, 800.0

            # Upper bound: nearest prior code in the same column
            upper_y = 0.0
            for j in range(i - 1, -1, -1):
                prev = line_items[j]
                pm = code_re.match(prev["text"])
                if pm and _get_col_idx(pm.group(1), n_cols, page_first_grade) == col_idx:
                    upper_y = prev["y"] + 12
                    break

            # Collect description lines from same column, above code
            desc_parts: list[str] = []
            for j in range(i - 1, max(i - 30, -1), -1):
                prev = line_items[j]
                if prev["y"] < upper_y:
                    break
                if prev["x0"] < desc_x_min - 5 or prev["x0"] > desc_x_max + 5:
                    continue
                pm = code_re.match(prev["text"])
                if pm:
                    if _get_col_idx(pm.group(1), n_cols, page_first_grade) == col_idx:
                        break
                    continue
                if prev["text"].startswith("Appendix"):
                    continue
                if prev["text"].startswith("*"):
                    continue
                if re.match(r"^(Grade|Kindergarten|The learner)", prev["text"]):
                    break
                if any(h in prev["text"] for h in _SPACED_HEADERS):
                    break
                if re.match(r"^\d{1,3}$", prev["text"]):
                    break
                desc_parts.insert(0, prev["text"])

            description = re.sub(r"\s+", " ", " ".join(desc_parts)).strip()
            description = re.sub(r"[\uf0a7\uf0b7]", "", description).strip()

            # Appendix reference on next line
            appendix_ref = None
            for k in range(i + 1, min(i + 3, len(line_items))):
                nt = line_items[k]["text"]
                if nt.startswith("Appendix"):
                    appendix_ref = nt.strip()
                    break
                if code_re.match(nt):
                    break

            enacted: dict = {
                "code": full_code,
                "description": description,
                "grades": grade_band,
            }
            if appendix_ref:
                enacted["appendix"] = appendix_ref
            enacted_by_rl[current_rl].append(enacted)

    # Deduplicate within each RL
    for rl in enacted_by_rl:
        seen: set[str] = set()
        unique: list[dict] = []
        for e in enacted_by_rl[rl]:
            if e["code"] not in seen:
                seen.add(e["code"])
                unique.append(e)
        enacted_by_rl[rl] = unique

    # ── Group RLs under their Learning Areas ─────────────────────────
    la_map: dict[str, list[str]] = {}
    for rl_code in sorted(enacted_by_rl.keys()):
        m_la = re.match(rf"{re.escape(prefix)}[–\-]([A-Z]+)\d+", rl_code)
        if m_la:
            la_map.setdefault(m_la.group(1), []).append(rl_code)

    learning_areas: list[dict] = []
    for la_code in ["M", "CR", "C", "R"]:
        if la_code not in la_map:
            continue
        la: dict = {
            "id": la_code,
            "title": LA_INFO[la_code],
            "description": la_descriptions.get(la_code, ""),
            "recursive_learnings": [],
        }
        for rl_code in la_map[la_code]:
            la["recursive_learnings"].append({
                "code": rl_code,
                "title": rl_titles.get(rl_code, ""),
                "enacted_learnings": enacted_by_rl.get(rl_code, []),
            })
        learning_areas.append(la)

    return {
        "learning_areas": learning_areas,
        "appendices": appendices,
    }


# ─────────────────────────────────────────────────────────────────────
# Grade-band → individual grades mapping
# ─────────────────────────────────────────────────────────────────────

ALL_GRADES = ["K", "1", "2", "3", "4", "5", "6", "7", "8"]

_BAND_GRADE_MAP: dict[str, list[str]] = {
    "K": ["K"], "1": ["1"], "2": ["2"], "3": ["3"], "4": ["4"],
    "5": ["5"], "6": ["6"], "7": ["7"], "8": ["8"],
    "K-1": ["K", "1"], "K-2": ["K", "1", "2"],
    "K-4": ["K", "1", "2", "3", "4"],
    "K-8": ALL_GRADES[:],
    "1-4": ["1", "2", "3", "4"], "1-6": ["1", "2", "3", "4", "5", "6"],
    "1-8": ["1", "2", "3", "4", "5", "6", "7", "8"],
    "2-4": ["2", "3", "4"],
    "3-4": ["3", "4"], "3-6": ["3", "4", "5", "6"], "3-8": ["3", "4", "5", "6", "7", "8"],
    "5-6": ["5", "6"], "5-8": ["5", "6", "7", "8"],
    "7-8": ["7", "8"],
}


def _grades_for_band(band: str) -> list[str]:
    normalized = band.replace("\u2013", "-").replace("–", "-")
    return _BAND_GRADE_MAP.get(normalized, ALL_GRADES[:])


def _filter_for_grade(learning_areas: list[dict], grade: str) -> list[dict]:
    """Return a copy of learning_areas containing only enacted learnings
    that apply to the given grade."""
    filtered_las: list[dict] = []
    for la in learning_areas:
        filtered_rls: list[dict] = []
        for rl in la["recursive_learnings"]:
            filtered_enacted = [
                e for e in rl["enacted_learnings"]
                if grade in _grades_for_band(e["grades"])
            ]
            if filtered_enacted:
                filtered_rls.append({
                    "code": rl["code"],
                    "title": rl["title"],
                    "enacted_learnings": filtered_enacted,
                })
        if filtered_rls:
            filtered_las.append({
                "id": la["id"],
                "title": la["title"],
                "description": la["description"],
                "recursive_learnings": filtered_rls,
            })
    return filtered_las


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────

def scrape_all_arts(
    output_dir: Path,
    progress_callback=None,
) -> dict[str, list]:
    """Scrape Arts Education K-8 (Dance, Dramatic Arts, Music, Visual Arts).

    Produces per-grade JSON files for each discipline, each containing
    the hierarchical structure (learning_areas → recursive_learnings →
    enacted_learnings) filtered to that grade.
    """
    results: dict[str, list] = {}
    tmp_dir = Path("/tmp/arts_pdfs")
    tmp_dir.mkdir(exist_ok=True)

    for disc_name, disc_info in DISCIPLINES.items():
        prefix = disc_info["prefix"]
        url = disc_info["url"]
        full_name = disc_info["full_name"]

        if progress_callback:
            progress_callback(f"Downloading {disc_name} K-8 framework PDF...")

        try:
            pdf_path = tmp_dir / f"{disc_name.lower().replace(' ', '_')}_k8.pdf"
            _download(url, pdf_path)
        except Exception as e:
            if progress_callback:
                progress_callback(f"ERROR downloading {disc_name}: {e}")
            continue

        if progress_callback:
            progress_callback(f"Parsing {disc_name} K-8 framework...")

        doc = fitz.open(str(pdf_path))
        parsed = _parse_discipline(doc, prefix)
        doc.close()

        all_las = parsed["learning_areas"]
        appendices = parsed["appendices"]

        for grade in ALL_GRADES:
            grade_las = _filter_for_grade(all_las, grade)
            if not grade_las:
                continue

            grade_label = "Kindergarten" if grade == "K" else f"Grade {grade}"
            output_data = {
                "subject": disc_name,
                "grade": grade_label,
                "grade_range": "Kindergarten to Grade 8",
                "framework_year": "2021",
                "document_title": full_name,
                "learning_areas": grade_las,
                "appendices": appendices,
            }

            filename = f"Arts_{disc_name.replace(' ', '')}_{grade}.json"
            filepath = output_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=4, ensure_ascii=False)

            total_enacted = sum(
                len(rl["enacted_learnings"])
                for la in grade_las
                for rl in la["recursive_learnings"]
            )
            result_key = f"{disc_name}_{grade}"
            results[result_key] = grade_las

            if progress_callback:
                progress_callback(
                    f"Saved {filename}: {len(grade_las)} learning areas, "
                    f"{total_enacted} enacted learnings"
                )

    return results
