"""Manitoba Arts Education Grades 9-12 scraper.

4 disciplines: Dance, Dramatic Arts, Music, Visual Arts.
Each has 4 Essential Learning Areas (Making, Creating, Connecting, Responding)
with 13 Recursive Learnings.

Outputs one JSON per discipline with hierarchical structure:
  learning_areas → recursive_learnings (with appendix refs)

Source PDFs: edu.gov.mb.ca/k12/cur/arts/docs/{disc}_9-12.pdf
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
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/dance_9-12.pdf",
        "prefix": "DA",
        "full_name": "Grades 9 to 12 Dance: Manitoba Curriculum Framework",
    },
    "Dramatic Arts": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/dramatic_arts_9-12.pdf",
        "prefix": "DR",
        "full_name": "Grades 9 to 12 Dramatic Arts: Manitoba Curriculum Framework",
    },
    "Music": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/music_9-12.pdf",
        "prefix": "M",
        "full_name": "Grades 9 to 12 Music: Manitoba Curriculum Framework",
    },
    "Visual Arts": {
        "url": "https://www.edu.gov.mb.ca/k12/cur/arts/docs/visual_9-12.pdf",
        "prefix": "VA",
        "full_name": "Grades 9 to 12 Visual Arts: Manitoba Curriculum Framework",
    },
}

AREAS = [
    ("M", "Making"),
    ("CR", "Creating"),
    ("C", "Connecting"),
    ("R", "Responding"),
]


def _download(url: str, dest: Path):
    if dest.exists() and dest.stat().st_size > 1000:
        return
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def _classify_area(code_suffix: str) -> str:
    if code_suffix.startswith("CR"):
        return "CR"
    if code_suffix.startswith("M"):
        return "M"
    if code_suffix.startswith("C"):
        return "C"
    if code_suffix.startswith("R"):
        return "R"
    return ""


def _parse_discipline(doc, prefix: str) -> dict:
    """Parse one 9-12 discipline PDF and return structured data."""
    toc = doc.get_toc()

    # ── Extract appendices from Contents pages ─────────────────────────
    appendices: list[dict] = []
    seen_app_codes: set[str] = set()
    short_desc = "Signposts for Breadth, Depth, and Transformation across Grades 9-12"

    for pg_idx in range(min(8, doc.page_count)):
        text = doc[pg_idx].get_text()
        lines = text.split("\n")
        for i, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line.startswith("Appendix"):
                continue

            # Lettered appendix: "Appendix X: Title..."
            m = re.match(r"Appendix\s+([A-Z]):\s*(.+)", line)
            if m:
                code = m.group(1)
                title_parts = [m.group(2).strip()]
                # Collect wrapped continuation lines
                for j in range(i + 1, min(i + 4, len(lines))):
                    nl = lines[j].strip()
                    if not nl or re.match(r"^\d+$", nl):
                        break
                    if nl.startswith("Appendix") or nl.startswith("Glossary") or nl.startswith("Bibliography"):
                        break
                    title_parts.append(nl)
                title = re.sub(r"\s+", " ", " ".join(title_parts)).strip()
                if code not in seen_app_codes:
                    seen_app_codes.add(code)
                    appendices.append({"code": code, "title": title, "short_description": short_desc})
                continue

            # Unlettered appendix: "Appendix: Title..."
            m2 = re.match(r"Appendix:\s*(.+)", line)
            if m2:
                title_parts = [m2.group(1).strip()]
                for j in range(i + 1, min(i + 4, len(lines))):
                    nl = lines[j].strip()
                    if not nl or re.match(r"^\d+$", nl):
                        break
                    if nl.startswith("Glossary") or nl.startswith("Bibliography"):
                        break
                    title_parts.append(nl)
                title = re.sub(r"\s+", " ", " ".join(title_parts)).strip()
                if "A" not in seen_app_codes:
                    seen_app_codes.add("A")
                    appendices.append({"code": "A", "title": title, "short_description": short_desc})

    # ── Extract RL data from "Recursive Learnings" overview page ──────
    rl_page = None
    for t in toc:
        if t[1] == "Recursive Learnings":
            rl_page = t[2]
            break

    la_descriptions: dict[str, str] = {}
    rl_titles: dict[str, str] = {}

    if rl_page:
        text = doc[rl_page - 1].get_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        current_la = None
        current_la_code = None
        la_desc_parts: list[str] = []
        capturing_la_desc = False
        current_rl = None
        rl_title_parts: list[str] = []

        rl_code_re = re.compile(
            rf"^({re.escape(prefix)}[–\-][A-Z]+\d+)\s*(.*)"
        )

        for l in lines:
            # Skip headers
            if re.match(r"^[A-Z]\s[a-z]\s[a-z]", l) or re.match(r"^\d+$", l):
                continue
            if l.startswith("Recursive Learnings") or "learning areas" in l or "Framework are" in l:
                continue
            if l.startswith("The recursive"):
                continue

            # LA header
            la_match = re.match(r"^(Making|Creating|Connecting|Responding)\s*\(([A-Z]+)\)", l)
            if la_match or l in ("Making (M)", "Creating (CR)", "Connecting (C)", "Responding (R)"):
                # Save previous RL
                if current_rl and rl_title_parts:
                    rl_titles[current_rl] = re.sub(r"\s+", " ", " ".join(rl_title_parts)).strip()
                    current_rl = None
                    rl_title_parts = []
                # Save previous LA desc
                if current_la_code and la_desc_parts:
                    la_descriptions[current_la_code] = re.sub(r"\s+", " ", " ".join(la_desc_parts)).strip()

                if la_match:
                    current_la = la_match.group(1)
                    current_la_code = la_match.group(2)
                else:
                    for code, name in AREAS:
                        if l.startswith(name):
                            current_la = name
                            current_la_code = code
                            break
                la_desc_parts = []
                capturing_la_desc = True
                continue

            # LA description (starts with "The learner" after LA header)
            if capturing_la_desc:
                if l.startswith("The learner"):
                    la_desc_parts = [l]
                    continue
                if la_desc_parts:
                    # Check if this is an RL code → stop capturing LA desc
                    rm = rl_code_re.match(l)
                    if rm:
                        capturing_la_desc = False
                        la_descriptions[current_la_code] = re.sub(r"\s+", " ", " ".join(la_desc_parts)).strip()
                        la_desc_parts = []
                        # Fall through to RL handling below
                    else:
                        la_desc_parts.append(l)
                        continue

            # RL code
            rm = rl_code_re.match(l)
            if rm:
                if current_rl and rl_title_parts:
                    rl_titles[current_rl] = re.sub(r"\s+", " ", " ".join(rl_title_parts)).strip()
                current_rl = rm.group(1).replace("-", "–").replace("–", "-")
                # Normalize to use regular hyphen
                current_rl = rm.group(1)
                # Normalize dashes
                current_rl = current_rl.replace("\u2013", "-").replace("–", "-")
                rest = rm.group(2).strip()
                rl_title_parts = [rest] if rest else []
                capturing_la_desc = False
                continue

            # RL title continuation
            if current_rl:
                rl_title_parts.append(l)

        # Save last RL and LA
        if current_rl and rl_title_parts:
            rl_titles[current_rl] = re.sub(r"\s+", " ", " ".join(rl_title_parts)).strip()
        if current_la_code and la_desc_parts:
            la_descriptions[current_la_code] = re.sub(r"\s+", " ", " ".join(la_desc_parts)).strip()

    # ── Get appendix refs per RL from their pages ─────────────────────
    rl_toc_entries = [(t[2], t[1]) for t in toc if t[0] == 3 and re.match(r"^[A-Z]+-", t[1])]
    rl_appendices: dict[str, list[str]] = {}

    for page_num, rl_code in rl_toc_entries:
        text = doc[page_num - 1].get_text()
        refs = sorted(set(re.findall(r"Appendix\s+([A-Z])", text)))
        norm_code = rl_code.replace("\u2013", "-").replace("–", "-")
        rl_appendices[norm_code] = refs

    # ── Build learning_areas structure ────────────────────────────────
    # Collect all RL codes from TOC
    all_rl_codes: list[str] = []
    for _, rl_code in rl_toc_entries:
        norm = rl_code.replace("\u2013", "-").replace("–", "-")
        all_rl_codes.append(norm)

    # Group RLs by LA
    la_rls: dict[str, list[str]] = {}
    for rl_code in all_rl_codes:
        parts = rl_code.split("-", 1)
        if len(parts) == 2:
            suffix = parts[1]
            area_code = _classify_area(suffix)
            la_rls.setdefault(area_code, []).append(rl_code)

    learning_areas: list[dict] = []
    for area_code, area_name in AREAS:
        rls_in_area = la_rls.get(area_code, [])
        rl_list: list[dict] = []
        for rl_code in rls_in_area:
            rl_list.append({
                "code": rl_code,
                "title": rl_titles.get(rl_code, ""),
                "appendices": rl_appendices.get(rl_code, []),
            })
        learning_areas.append({
            "id": area_code,
            "title": area_name,
            "description": la_descriptions.get(area_code, f"The learner develops language and practices for {area_name.lower()}."),
            "recursive_learnings": rl_list,
        })

    return {
        "learning_areas": learning_areas,
        "appendices": appendices,
    }


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────

def scrape_all_arts912(
    output_dir: Path,
    progress_callback=None,
) -> dict[str, list]:
    """Scrape Arts Education Grades 9-12 (Dance, Drama, Music, Visual Arts).

    Produces one JSON per discipline with hierarchical structure:
      learning_areas → recursive_learnings (with appendix refs)
    """
    results: dict[str, list] = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path("/tmp/arts912_pdfs")
    tmp_dir.mkdir(exist_ok=True)

    for disc_name, disc_info in DISCIPLINES.items():
        prefix = disc_info["prefix"]
        url = disc_info["url"]
        full_name = disc_info["full_name"]

        if progress_callback:
            progress_callback(f"Downloading {disc_name} 9-12 PDF...")

        try:
            pdf_path = tmp_dir / f"{disc_name.lower().replace(' ', '_')}_912.pdf"
            _download(url, pdf_path)
        except Exception as e:
            if progress_callback:
                progress_callback(f"ERROR downloading {disc_name}: {e}")
            continue

        if progress_callback:
            progress_callback(f"Parsing {disc_name} 9-12 framework...")

        doc = fitz.open(str(pdf_path))
        parsed = _parse_discipline(doc, prefix)
        doc.close()

        output_data = {
            "subject": f"{disc_name} 2015",
            "grade_range": "Grades",
            "framework_year": "2015",
            "document_title": full_name,
            "learning_areas": parsed["learning_areas"],
            "appendices": parsed["appendices"],
        }

        safe_name = disc_name.replace(" ", "")
        filename = f"Arts_{safe_name}_9-12.json"
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)

        n_rls = sum(len(la["recursive_learnings"]) for la in parsed["learning_areas"])
        results[disc_name] = parsed["learning_areas"]

        if progress_callback:
            progress_callback(
                f"Saved {filename}: {len(parsed['learning_areas'])} learning areas, "
                f"{n_rls} recursive learnings, {len(parsed['appendices'])} appendices"
            )

    return results
