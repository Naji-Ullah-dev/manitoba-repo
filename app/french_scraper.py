"""Manitoba French (English Program) curriculum scraper (K-12).

Two programs:
  - Early Start French (K-3): Oral Communication only (Listening + Speaking)
  - French: Communication and Culture (Gr 4-12): 4 strands
    (Oral Communication, Reading, Writing, Culture)

GLOs and SLOs extracted from official curriculum framework PDFs.
SLO codes assigned as: FR.{grade}.{strand_code}.{num}
  Strand codes: OC=Oral Communication, R=Reading, W=Writing, CU=Culture

Source docs:
  K-3: edu.gov.mb.ca/m12/frpub/ped/fdb/cadre_m-3/docs/doc_complet.pdf
  4-12: edu.gov.mb.ca/m12/frpub/ped/fdb/cadre_4-12/docs/ (per-grade table PDFs)
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GLO definitions (constant across grades within each program)
# ---------------------------------------------------------------------------

GLOS_K3 = {
    "OC1": "Listen in order to understand the communicated message.",
    "OC2": "Communicate ideas orally and interact with others.",
}

GLOS_4_12 = {
    "OC1": "Listen in order to understand the communicated message.",
    "OC2": "Communicate orally and interact spontaneously, keeping in mind the message, fluency and accuracy.",
    "R": "Read a variety of texts for various purposes, and demonstrate understanding orally, in writing or visually.",
    "W": "Plan and write coherent texts to communicate the message.",
    "CU1": "Demonstrate a general knowledge of both francophone cultures and the advantages of learning French.",
    "CU2": "Apply knowledge of francophone cultures to interactions with others (intercultural).",
}

# ---------------------------------------------------------------------------
# SLOs per grade (hardcoded from official PDF text extraction)
# ---------------------------------------------------------------------------

# K-3: Early Start French — Oral Communication only
# K and 1 share the same outcomes; 2 and 3 share the same outcomes

_K1_SLOS = [
    ("OC", "Listening", "Students listen (with the support of visuals) and demonstrate understanding of simple spoken French modeled by the teacher."),
    ("OC", "Speaking", "Students communicate a simple message correctly (pronunciation and intonation as modeled by the teacher)."),
]

_GR2_3_SLOS = [
    ("OC", "Listening", "Students listen (with the support of visuals) and demonstrate understanding of simple spoken French as modeled by the teacher."),
    ("OC", "Speaking", "Students communicate a simple message correctly (pronunciation and intonation as modeled by the teacher)."),
]

# Gr 4: Communication and Culture
_GR4_SLOS = [
    ("OC", "Listening", "Students listen, with visual support as needed, and demonstrate comprehension."),
    ("OC", "Message", "Students communicate ideas effectively and logically in complete simple sentences as modeled by the teacher."),
    ("OC", "Fluency", "Students use appropriate vocabulary and expressions as modeled by the teacher to communicate a message with spontaneity."),
    ("OC", "Fluency", "Students use rhythm, pace and intonation to communicate and to interact as modeled by the teacher."),
    ("OC", "Accuracy", "Students correctly use vocabulary and syntax of the French language as modeled by the teacher."),
    ("OC", "Accuracy", "Students use simple affirmative, negative and interrogative linguistic structures, primarily in the present tense (related to themes)."),
    ("OC", "Accuracy", "Students demonstrate accuracy in pronunciation as modeled by the teacher."),
    ("R", "Message", "Students read and understand the global meaning of narrative and expository texts."),
    ("R", "Message", "Students respond to text."),
    ("R", "Fluency and Accuracy", "Students read grade appropriate texts aloud."),
    ("W", "Message", "Students communicate ideas clearly and logically in complete simple sentences as modeled by the teacher."),
    ("W", "Fluency", "Students write clearly and with fluency a variety of texts on familiar topics, in complete simple sentences and in simple paragraphs, as modeled by the teacher."),
    ("W", "Fluency", "Students use appropriate vocabulary and linguistic structures to convey their message."),
    ("W", "Accuracy", "Students manage their writing, keeping in mind the rules and syntax of the French language."),
    ("CU", "Culture", "Students identify elements of francophone cultures."),
    ("CU", "Culture", "Students make links to personal life."),
    ("CU", "Culture", "Students use appropriate vocabulary according to the purpose and to the context of communication."),
    ("CU", "Culture", "Students identify advantages of learning French."),
    ("CU", "Culture", "Students identify themselves as French language learners."),
]

# Gr 5-6
_GR5_6_SLOS = [
    ("OC", "Listening", "Students listen, with visual support as needed, and demonstrate comprehension."),
    ("OC", "Message", "Students communicate ideas effectively and logically in complete sentences as modeled by the teacher."),
    ("OC", "Message", "Students communicate ideas with simple details as modeled by the teacher."),
    ("OC", "Fluency", "Students use appropriate vocabulary and expressions as modeled by the teacher to communicate a message with spontaneity."),
    ("OC", "Fluency", "Students use appropriate rhythm, pace and intonation to communicate and to interact as modeled by the teacher."),
    ("OC", "Accuracy", "Students correctly use vocabulary and syntax of the French language as modeled by the teacher."),
    ("OC", "Accuracy", "Students use simple and compound linguistic structures in the affirmative, negative and interrogative forms."),
    ("OC", "Accuracy", "Students use the present, imperative, past and future tenses as needed for their communicative needs (related to themes)."),
    ("OC", "Accuracy", "Students demonstrate accuracy in pronunciation as modeled by the teacher."),
    ("R", "Message", "Students read and understand the global meaning of narrative and expository texts."),
    ("R", "Message", "Students respond to text."),
    ("R", "Fluency and Accuracy", "Students read grade appropriate texts aloud."),
    ("W", "Message", "Students communicate ideas clearly and logically in complete sentences and in paragraphs, as modeled by the teacher."),
    ("W", "Fluency", "Students write clearly and with fluency a variety of texts on familiar topics, in complete sentences and in simple paragraphs, as modeled by the teacher."),
    ("W", "Fluency", "Students use appropriate vocabulary and linguistic structures to convey their message."),
    ("W", "Accuracy", "Students manage their writing, keeping in mind the rules and syntax of the French language."),
    ("CU", "Culture", "Students identify elements of francophone cultures."),
    ("CU", "Culture", "Students make links to personal life."),
    ("CU", "Culture", "Students use appropriate vocabulary according to the purpose and to the context of communication."),
    ("CU", "Culture", "Students identify advantages of learning French."),
    ("CU", "Culture", "Students identify themselves as French language learners."),
]

# Gr 7-8
_GR7_8_SLOS = [
    ("OC", "Listening", "Students listen, with visual support as needed, and demonstrate comprehension."),
    ("OC", "Message", "Students communicate ideas effectively and logically in complete sentences as modeled by the teacher."),
    ("OC", "Message", "Students elaborate ideas with details, opinions, and examples as modeled by the teacher."),
    ("OC", "Fluency", "Students use appropriate vocabulary and expressions as modeled by the teacher to communicate a message with spontaneity."),
    ("OC", "Fluency", "Students use appropriate rhythm, pace and intonation to communicate and to interact as modeled by the teacher."),
    ("OC", "Accuracy", "Students correctly use vocabulary and syntax of the French language as modeled by the teacher."),
    ("OC", "Accuracy", "Students use simple and compound linguistic structures in the affirmative, negative, and interrogative forms."),
    ("OC", "Accuracy", "Students use the present, past, future and imperative tenses (related to themes)."),
    ("OC", "Accuracy", "Students demonstrate accuracy in pronunciation as modeled by the teacher."),
    ("R", "Message", "Students read and understand the global meaning of narrative and expository texts."),
    ("R", "Message", "Students respond to text."),
    ("R", "Fluency and Accuracy", "Students read grade appropriate texts aloud."),
    ("W", "Message", "Students communicate ideas clearly and logically in paragraphs following examples modeled by the teacher."),
    ("W", "Fluency", "Students write a variety of coherent texts on familiar topics with some autonomy."),
    ("W", "Fluency", "Students use appropriate vocabulary and linguistic structures to convey their message."),
    ("W", "Accuracy", "Students manage their writing, keeping in mind the rules and syntax of the French language."),
    ("CU", "Culture", "Students identify elements of francophone cultures."),
    ("CU", "Culture", "Students make links to personal life."),
    ("CU", "Culture", "Students use appropriate vocabulary according to the purpose and to the context of communication."),
    ("CU", "Culture", "Students identify the reasons and the advantages of learning French."),
    ("CU", "Culture", "Students identify themselves as French language learners."),
]

# Gr 9-10
_GR9_10_SLOS = [
    ("OC", "Listening", "Students listen and demonstrate comprehension."),
    ("OC", "Message", "Students communicate ideas effectively and logically as modeled by the teacher and other French speakers, including recorded oral documents."),
    ("OC", "Message", "Students elaborate ideas with details, opinions and examples."),
    ("OC", "Fluency", "Students use appropriate vocabulary and expressions to communicate a message with spontaneity."),
    ("OC", "Fluency", "Students use appropriate rhythm, pace and intonation to communicate and to interact."),
    ("OC", "Accuracy", "Students correctly use vocabulary and syntax of the French language related to the topics and communicative intent."),
    ("OC", "Accuracy", "Students use affirmative, negative and interrogative linguistic structures in compound and complex sentences."),
    ("OC", "Accuracy", "Students use the present, imperative, past, imperfect, future and conditional tenses, among others, as needed, for communicative purposes related to the topic."),
    ("OC", "Accuracy", "Students demonstrate accuracy in pronunciation."),
    ("R", "Message", "Students read and understand the global meaning and key points of narrative, expository, and poetic texts, according to the purpose for reading."),
    ("R", "Message", "Students respond to text."),
    ("R", "Fluency and Accuracy", "Students read a variety of texts aloud."),
    ("W", "Message", "Students develop and communicate ideas clearly and logically on familiar topics using models as support."),
    ("W", "Fluency", "Students write a variety of coherent and organized texts."),
    ("W", "Fluency", "Students use vocabulary and linguistic structures that are appropriate for the topic and communicative intent."),
    ("W", "Accuracy", "Students manage their writing, keeping in mind the rules and syntax of the French language."),
    ("CU", "Culture", "Students describe elements of francophone cultures."),
    ("CU", "Culture", "Students make links to personal life."),
    ("CU", "Culture", "Students use appropriate vocabulary according to the purpose and to the context of communication."),
    ("CU", "Culture", "Students identify reasons and advantages of learning French."),
    ("CU", "Culture", "Students identify themselves as French language learners."),
]

# Gr 11-12
_GR11_12_SLOS = [
    ("OC", "Listening", "Students listen and demonstrate comprehension."),
    ("OC", "Message", "Students communicate ideas effectively and logically as modeled by the teacher and other French speakers, including recorded oral documents."),
    ("OC", "Message", "Students elaborate ideas with details, opinions, and examples."),
    ("OC", "Fluency", "Students use appropriate vocabulary and expressions to communicate a message with spontaneity."),
    ("OC", "Fluency", "Students use appropriate rhythm, pace and intonation to communicate and to interact."),
    ("OC", "Accuracy", "Students correctly use vocabulary and syntax of the French language related to the topics and communicative intent."),
    ("OC", "Accuracy", "Students use affirmative, negative and interrogative linguistic structures in compound, and complex sentences."),
    ("OC", "Accuracy", "Students use the present, imperative, past, imperfect, future and conditional tenses, among others, as needed, for communicative purposes related to the topic."),
    ("OC", "Accuracy", "Students demonstrate accuracy in pronunciation."),
    ("R", "Message", "Students read and understand the overall message, and the details necessary of narrative, expository, persuasive and poetic texts, according to the purpose for reading."),
    ("R", "Message", "Students respond to text."),
    ("R", "Fluency and Accuracy", "Students read a variety of texts aloud."),
    ("W", "Message", "Students develop and communicate ideas coherently, effectively, and independently on a variety of topics."),
    ("W", "Fluency", "Students write a variety of coherent and organized texts."),
    ("W", "Fluency", "Students use vocabulary and linguistic structures that are appropriate for the topic and communicative intent."),
    ("W", "Accuracy", "Students manage their writing, keeping in mind the rules, and syntax of the French language."),
    ("CU", "Culture", "Students explain elements of francophone cultures."),
    ("CU", "Culture", "Students make links to personal life."),
    ("CU", "Culture", "Students use appropriate vocabulary according to the purpose and to the context of communication."),
    ("CU", "Culture", "Students identify the reasons and the advantages of learning French."),
    ("CU", "Culture", "Students identify themselves as French language learners."),
]

# Map grades to their SLO sets
GRADE_SLOS: dict[str, list[tuple[str, str, str]]] = {
    "K": _K1_SLOS,
    "1": _K1_SLOS,
    "2": _GR2_3_SLOS,
    "3": _GR2_3_SLOS,
    "4": _GR4_SLOS,
    "5": _GR5_6_SLOS,
    "6": _GR5_6_SLOS,
    "7": _GR7_8_SLOS,
    "8": _GR7_8_SLOS,
    "9": _GR9_10_SLOS,
    "10": _GR9_10_SLOS,
    "11": _GR11_12_SLOS,
    "12": _GR11_12_SLOS,
}

STRAND_NAMES = {
    "OC": "Oral Communication",
    "R": "Reading",
    "W": "Writing",
    "CU": "Culture",
}


def _build_grade(grade: str) -> list[dict]:
    """Build outcome list for a single grade."""
    slos = GRADE_SLOS[grade]
    is_early = grade in ("K", "1", "2", "3")
    glos = GLOS_K3 if is_early else GLOS_4_12

    outcomes: list[dict] = []
    strand_counters: dict[str, int] = {}

    for strand_code, sub_category, description in slos:
        strand_counters.setdefault(strand_code, 0)
        strand_counters[strand_code] += 1
        num = strand_counters[strand_code]

        slo_code = f"FR.{grade}.{strand_code}.{num}"
        strand_name = STRAND_NAMES.get(strand_code, strand_code)

        # Map strand to relevant GLOs
        if strand_code == "OC":
            glo_list = [{"code": "OC1", "description": glos["OC1"]},
                        {"code": "OC2", "description": glos["OC2"]}]
        elif strand_code == "R" and not is_early:
            glo_list = [{"code": "R", "description": glos["R"]}]
        elif strand_code == "W" and not is_early:
            glo_list = [{"code": "W", "description": glos["W"]}]
        elif strand_code == "CU" and not is_early:
            glo_list = [{"code": "CU1", "description": glos["CU1"]},
                        {"code": "CU2", "description": glos["CU2"]}]
        else:
            glo_list = []

        outcome = {
            "id": slo_code,
            "code": slo_code,
            "strand": strand_name,
            "sub_category": sub_category,
            "description": description,
            "glos": glo_list,
            "course": f"French (English Program) {'Early Start' if is_early else 'Communication and Culture'} Grade {grade}" if grade != "K" else "French (English Program) Early Start Kindergarten",
        }
        outcomes.append(outcome)

    return outcomes


def scrape_all_french(output_dir: Path, progress_callback=None) -> dict[str, list]:
    """Generate French (English Program) K-12 JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, list] = {}
    grades = ["K"] + [str(g) for g in range(1, 13)]

    for i, grade in enumerate(grades, 1):
        label = f"Kindergarten" if grade == "K" else f"Grade {grade}"
        if progress_callback:
            progress_callback(f"[{i}/13] Building French {label}...")

        outcomes = _build_grade(grade)

        filename = f"French_{'K' if grade == 'K' else f'Gr{grade}'}.json"
        filepath = output_dir / filename

        # Group outcomes by strand for cluster structure
        strand_groups: dict[str, list[dict]] = {}
        for o in outcomes:
            strand_groups.setdefault(o["strand"], []).append(o)

        clusters = []
        for strand_name, strand_outcomes in strand_groups.items():
            clusters.append({
                "id": f"FR_{grade}_{strand_name.replace(' ', '_')}",
                "title": strand_name,
                "specific_learning_outcomes": strand_outcomes,
            })

        output_data = {
            "subject": "French (English Program)",
            "grade": grade,
            "course": f"French (English Program) {'Early Start' if grade in ('K','1','2','3') else 'Communication and Culture'} Grade {grade}" if grade != "K" else "French (English Program) Early Start Kindergarten",
            "framework_year": "Legacy Framework",
            "clusters": clusters,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        all_results[filename] = outcomes
        if progress_callback:
            progress_callback(f"  → {filename}: {len(outcomes)} outcomes")

    total = sum(len(v) for v in all_results.values())
    if progress_callback:
        progress_callback(f"\nFrench (English Program): {total} outcomes across {len(all_results)} grades")

    return all_results
