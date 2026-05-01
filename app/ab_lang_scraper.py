"""Manitoba Aboriginal Languages and Cultures K-12 scraper.

Parses the K-12 Aboriginal Languages and Cultures Framework of Outcomes PDF.
4 GLOs, 39 cluster/strand codes, 6 grade bands (K-2, 3-4, 5-6, 7-8, 9-10, 11-12).
SLO codes: {cluster}: {letter}-{grade_end} (e.g. 1.1.1: A-2)

Source: edu.gov.mb.ca/k12/abedu/framework/k-12_ab_lang.pdf
"""

import json
import logging
import re
from pathlib import Path

import fitz
import httpx

logger = logging.getLogger(__name__)

PDF_URL = "https://www.edu.gov.mb.ca/k12/abedu/framework/k-12_ab_lang.pdf"

_SLO_RE = re.compile(r"^(\d+\.\d+\.\d+):\s*([A-Z])-(\d+)\s+(.*)")

GRADE_BANDS = {
    "2": "K-2",
    "4": "3-4",
    "6": "5-6",
    "8": "7-8",
    "10": "9-10",
    "12": "11-12",
}

GRADE_BAND_ORDER = ["K-2", "3-4", "5-6", "7-8", "9-10", "11-12"]

GLO_DESCRIPTIONS = {
    "1": {
        "code": "GLO 1",
        "title": "Language Competence",
        "description": "Students will use the Aboriginal language effectively and competently in listening, viewing, speaking, reading, representing, and writing.",
    },
    "2": {
        "code": "GLO 2",
        "title": "Language Learning Strategies",
        "description": "Students will develop and use strategies to enhance the effectiveness of learning and communicating in the Aboriginal language.",
    },
    "3": {
        "code": "GLO 3",
        "title": "Language Use in Context",
        "description": "Students will use the Aboriginal language in a variety of situations and for a variety of purposes.",
    },
    "4": {
        "code": "GLO 4",
        "title": "Cultural and Linguistic Diversity",
        "description": "Students will explore and value cultural and linguistic diversity and gain intercultural understanding.",
    },
}

CLUSTER_NAMES = {
    "1.1": "Listening, Observing, and Responding",
    "1.2": "Speaking, Sharing, and Presenting",
    "1.3": "Reading, Viewing, and Comprehending",
    "1.4": "Writing, Representing, and Producing",
    "2.1": "Cognitive Strategies",
    "2.2": "Metacognitive Strategies",
    "2.3": "Social Strategies",
    "2.4": "Affective Strategies",
    "3.1": "Home",
    "3.2": "School",
    "3.3": "Within the Community",
    "3.4": "Outside the Community",
    "4.1": "Specific Aboriginal Culture",
    "4.2": "Other Cultures: Connections and Influences",
    "4.3": "Cultural Diversity",
    "4.4": "Linguistic Diversity",
}

STRAND_NAMES = {
    "1.1.1": "Aural/Oral Texts",
    "1.1.2": "Visual Texts",
    "1.1.3": "Phonology",
    "1.1.4": "Patterns of Social Interaction",
    "1.2.1": "Text Forms",
    "1.2.2": "Formal and Informal Speech (Register)",
    "1.2.3": "Phonology",
    "1.2.4": "Lexicon (Vocabulary)",
    "1.3.1": "Attend to Texts",
    "1.3.2": "Coherence",
    "1.3.3": "Grammatical Elements",
    "1.4.1": "Text Forms",
    "1.4.2": "Grammatical Structures",
    "1.4.3": "Cohesion",
    "1.4.4": "Orthography",
    "2.1.1": "Cognitive Strategies",
    "2.2.1": "Metacognitive Strategies",
    "2.3.1": "Social Strategies",
    "2.4.1": "Affective Strategies",
    "3.1.1": "Home: Family and Relationships",
    "3.1.2": "Home: Daily Living",
    "3.2.1": "School: Life and Learning",
    "3.2.2": "School: Leadership",
    "3.2.3": "School: The Natural World",
    "3.3.1": "Community: Places and Events",
    "3.3.2": "Community: Services",
    "3.3.3": "Community: People and Roles",
    "3.4.1": "Outside the Community: Travel",
    "3.4.2": "Outside the Community: Technology and Media",
    "4.1.1": "History and Traditions",
    "4.1.2": "Beliefs, Values, and Attitudes",
    "4.1.3": "Land, Environment, and Resources",
    "4.2.1": "Intercultural Awareness",
    "4.2.2": "Cross-Cultural Connections",
    "4.2.3": "Historical and Contemporary Influences",
    "4.3.1": "Cultural Diversity Awareness",
    "4.3.2": "Contributions and Achievements",
    "4.4.1": "Linguistic Diversity Awareness",
    "4.4.2": "Language Preservation and Revitalization",
}


def _download_pdf() -> bytes:
    resp = httpx.get(PDF_URL, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def _extract_slos(doc: fitz.Document) -> list[dict]:
    """Extract all SLOs from the PDF."""
    all_slos: list[dict] = []

    for p in range(31, min(140, doc.page_count)):
        text = doc[p].get_text()
        lines = text.split("\n")

        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            m = _SLO_RE.match(stripped)
            if m:
                cluster_code = m.group(1)
                letter = m.group(2)
                grade_end = m.group(3)
                desc = m.group(4).strip()

                j = i + 1
                while j < len(lines):
                    next_line = lines[j].strip()
                    if not next_line:
                        j += 1
                        continue
                    if _SLO_RE.match(next_line):
                        break
                    if next_line.startswith("Students will") or next_line.startswith("GLO"):
                        break
                    if "Kindergarten to Grade 12" in next_line:
                        break
                    if re.match(r"^[A-Z\s]{10,}$", next_line):
                        break
                    desc += " " + next_line
                    j += 1

                band = GRADE_BANDS.get(grade_end, f"?-{grade_end}")
                glo_num = cluster_code.split(".")[0]
                cluster_key = ".".join(cluster_code.split(".")[:2])

                slo = {
                    "code": f"{cluster_code}: {letter}-{grade_end}",
                    "cluster_code": cluster_code,
                    "strand": STRAND_NAMES.get(cluster_code, cluster_code),
                    "cluster": CLUSTER_NAMES.get(cluster_key, cluster_key),
                    "description": desc.strip(),
                    "grade_band": band,
                    "glo": GLO_DESCRIPTIONS.get(glo_num, {}),
                }
                all_slos.append(slo)
            i += 1

    return all_slos


def scrape_all_ab_lang(output_dir: Path, progress_callback=None) -> dict[str, list]:
    """Scrape Aboriginal Languages K-12 and produce per-grade-band JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback("Downloading Aboriginal Languages K-12 PDF...")

    pdf_bytes = _download_pdf()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if progress_callback:
        progress_callback(f"Parsing {doc.page_count}-page PDF...")

    all_slos = _extract_slos(doc)
    doc.close()

    if progress_callback:
        progress_callback(f"Found {len(all_slos)} total SLOs")

    # Group by grade band
    band_groups: dict[str, list] = {}
    for slo in all_slos:
        band = slo["grade_band"]
        band_groups.setdefault(band, []).append(slo)

    results: dict[str, list] = {}

    for band in GRADE_BAND_ORDER:
        slos = band_groups.get(band, [])
        if not slos:
            continue

        filename = f"AboriginalLanguages_{band.replace('-', '_')}.json"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(slos, f, indent=2, ensure_ascii=False)

        results[filename] = slos
        if progress_callback:
            progress_callback(f"  → {filename}: {len(slos)} SLOs")

    total = sum(len(v) for v in results.values())
    if progress_callback:
        progress_callback(f"\nAboriginal Languages K-12: {total} SLOs across {len(results)} grade bands")

    return results
