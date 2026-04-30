# Manitoba Legacy Curriculum Scraper

Scrapes curriculum data from Manitoba's legacy education site (`edu.gov.mb.ca/k12/cur/`) and outputs structured JSON files per grade.

## Currently Supported Subjects

| Subject | Grades | Source | Outcomes |
|---------|--------|--------|----------|
| Science | K-11 | PDF (K-4, 5-8, S1, S2 bands) | ~1,170 SLOs |
| Social Studies | K-10 | PDF (K-8 framework + Gr 9-10) | ~730 outcomes |
| Mathematics | K-8 | PDF (K-8 framework) | ~190 outcomes |
| Physical Education/Health Education | K-10 | HTML grade pages | ~810 outcomes |
| Career Development | 9-12 | PDF (per-grade two-column) | ~240 outcomes |
| English Language Arts | S1-S4 (Gr 9-12) | PDF (per-GLO and full docs) | ~420 outcomes |
| Arts Education - Dance | K-8 (per grade) | PDF (K-8 framework) | ~100 per discipline |
| Arts Education - Drama | K-8 (per grade) | PDF (K-8 framework) | ~100 per discipline |
| Arts Education - Music | K-8 (per grade) | PDF (K-8 framework) | ~130 per discipline |
| Arts Education - Visual Arts | K-8 (per grade) | PDF (K-8 framework) | ~120 per discipline |

### Not Scrapable

- **ELA K-8**: Full outcome documents are copyright-restricted and not available online. Only the 2020 Curriculum Framework (high-level, no SLO codes) is published.
- **Indigenous Education**: 468-page narrative format, no coded SLOs — uses Essential Questions instead.
- **Math/Social Studies Senior Years**: Redirected to the new Framework for Learning site.
- **Technology Education, ICT, Diversity Ed**: Implementation guides/resources, no structured outcomes.

## Output Format

Each grade produces a JSON file like `Science_Grade_K.json`:

```json
{
    "subject": "Science",
    "grade": "K",
    "course": "K-4 Science",
    "framework_year": "Framework 1999",
    "clusters": [
        {
            "id": "Trees",
            "title": "Trees",
            "description": "In Kindergarten, an investigation of trees...",
            "specific_learning_outcomes": [
                {
                    "code": "K-1-01",
                    "description": "Use appropriate vocabulary related to their investigations of trees...",
                    "glo": ["C5", "D1", "D5"],
                    "glo_description": [
                        "C5. demonstrate curiosity, skepticism, creativity...",
                        "D1. understand essential life structures...",
                        "D5. understand the composition of the Earth's atmosphere..."
                    ]
                }
            ]
        }
    ]
}
```

## Setup

```bash
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 and click the subject buttons to scrape.

## Docker

```bash
docker build -t mb-scraper .
docker run -p 8000:8000 mb-scraper
```

## Architecture

- `app/main.py` — FastAPI web app with UI and API endpoints
- `app/science_scraper.py` — Science K-11 (PDF parsing with PyMuPDF)
- `app/socstud_scraper.py` — Social Studies K-10 (PDF parsing)
- `app/math_scraper.py` — Mathematics K-8 (PDF parsing)
- `app/pehe_scraper.py` — Physical Education / Health Education K-10 (HTML parsing)
- `app/cardev_scraper.py` — Career Development 9-12 (PDF two-column extraction)
- `app/ela_scraper.py` — English Language Arts S1-S4 (PDF parsing)
- `app/arts_scraper.py` — Arts Education K-8 per grade (Dance, Drama, Music, Visual Arts)
- `app/glo_definitions.py` — Science GLO reference definitions
