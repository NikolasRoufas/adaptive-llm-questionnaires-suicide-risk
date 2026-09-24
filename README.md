# Adaptive LLM-Generated Questionnaires for Suicide Risk Assessment

### A Clinical Pilot in Greece

[![Conference](https://img.shields.io/badge/NICE%20TEAS%20Europe-2026-0B3D91)](https://doi.org/10.17605/osf.io/vcjrm)
[![OSF](https://img.shields.io/badge/OSF-10.17605%2Fosf.io%2Fvcjrm-2E7D32)](https://doi.org/10.17605/osf.io/vcjrm)
[![Ethics](https://img.shields.io/badge/Ethics-KL--2025--07%2FETH-6A1B9A)](#ethics--safety)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)](#repository-layout)

> **Companion code** for the NICE TEAS Europe 2026 paper.  
> Clinician-supervised, LLM-assisted generation and weekly adaptation of personalized suicide-risk questionnaires — supporting clinical judgment, not replacing it.

**Paper PDF / publisher DOI:** _link forthcoming_ · **OSF registration:** [doi:10.17605/osf.io/vcjrm](https://doi.org/10.17605/osf.io/vcjrm)

---

## Abstract

This study presents an early-stage clinical pilot of an adaptive system that leverages large language models (LLMs) to generate personalized questionnaires for suicide risk assessment within a preventive therapeutic context. The framework combines LLM-driven question generation, fuzzy logic–based adaptation, and patient history to iteratively tailor questionnaire content under continuous clinician supervision. The system has been deployed in a psychosocial rehabilitation setting in Athens, Greece (KLIMAKA), where dynamically adapted questionnaires are integrated into routine clinical care.

---

## Contributions

1. **LLM-based question generation** grounded in patient history and clinician prompts (Google Sheets HITL).
2. **Weight-based / fuzzy adaptive selection** using five Likert engagement dimensions.
3. **Human-in-the-loop validation** — clinicians score items, write session notes, and gate every replacement cycle.
4. **Longitudinal analytics exports** (CSV / JSON / plots) for transparency and secondary analysis.

---

## Method (pipeline)

```text
Patient history (Sheets)
        │
        ▼
   [task0]  LLM → initial questionnaire (5 categories × 4 items = 20)
        │
        ▼
   [task1_preparation]  Parse Greek markdown → patientN tab
        │
        ▼
   Clinician session (HITL in Sheets)
        · 5 Likert scores per question
        · meeting notes
        │
        ▼
   [task1]  Update weights → replace 2 lowest / category → LLM replacements
        │
        ▼
   [task1_analyze_results] + [task1_visualize_results]
```

### Adaptation rule

For each question \(i\) with composite engagement score \(f_i\) (mean of 5 Likert dims):

\[
w'_i = w_i + \alpha (f_i - \mu), \quad \alpha = 0.2,\ \mu = 4.0
\]

Per category, the **two lowest**-weight items are candidates for replacement under clinician validation.

### Clinician / engagement dimensions

| Dimension | Role |
|-----------|------|
| Coherence | Linguistic / clinical clarity |
| Emotional Resonance | Affective fit |
| Perceived Helpfulness | Clinical usefulness |
| Motivational Impact | Activation potential |
| Engagement | Meaningful response likelihood |

---

## System overview

| Is | Is not |
|----|--------|
| Batch Python orchestrator over Google Sheets | Real-time chat / patient-facing app |
| LLM for **generation & replacement** of questions | LLM for diagnosis or risk scoring |
| Clinician HITL in Sheets | Automated clinical approval API |
| Weight-driven adaptive questionnaire | Fixed static PHQ-9 / C-SSRS form |

---

## Repository layout

```text
README.md                 # This file
LICENSE / NOTICE          # MIT + clinical constraints
CITATION.cff
pyproject.toml            # Installable package metadata
requirements.txt
main.py                   # Thin CLI entry point
config/
  config.example.ini      # Copy → config.ini (local only)
scripts/
  run.sh                  # Run all pipeline stages
src/adaptive_questionnaires/
  pipeline.py             # Controllers for task0 / task1 / analyze / plot
  core/mark_i.py          # Config + logging singleton
  clients/                # Google Sheets, OpenAI, Dropbox
outputs/                  # Local figures (gitignored contents)
```

Package layout follows the standard Python `src/` pattern (one package — not a mix of `lib/` and `src/`).

---

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional: pip install -e .
cp config/config.example.ini config/config.ini
# Fill OpenAI key, Google OAuth path, spreadsheet IDs
```

Place Sheets OAuth JSON under `config/secrets/`, then:

```bash
python main.py -o task0
python main.py -o task1_preparation
python main.py -o task1
python main.py -o task1_analyze_results
python main.py -o task1_visualize_results
```

Or: `bash scripts/run.sh`  
Or: `python -m adaptive_questionnaires -o task1` (after `pip install -e .`)

---

## Ethics & safety

- **Protocol:** KL-2025-07/ETH (KLIMAKA Scientific Committee, July 2025; Declaration of Helsinki).
- **Clinical role:** Decision-support for licensed clinicians only; mandatory therapist validation before delivery.
- **Crisis (Greece):** **1018** (KLIMAKA). Elsewhere: local emergency / IASP resources.
- **Data:** Clinical exports and secrets are local-only (see [`.gitignore`](.gitignore) and [`NOTICE`](NOTICE)).

---

## Authors

| Author | Affiliation |
|--------|-------------|
| **Dimitrios Georgiou** | Department of Informatics, Ionian University |
| **Akis Makrigiannis** | Klimaka NGO, Athens |
| **Vassilis C. Gerogiannis** | Department of Digital Systems, University of Thessaly |
| **Andreas Kanavos** | Department of Informatics, Ionian University |

Contact: `dgeorgiou@ionio.gr`

---

## Acknowledgments

We thank the clinicians and staff at **KLIMAKA** and collaborators involved in the NICE TEAS Europe 2026 presentation for enabling this supervised clinical pilot.

---

## How to cite

If you use this **code**, **method**, or **results**, please cite the paper:

Georgiou, D., Makrigiannis, A., Gerogiannis, V. C., & Kanavos, A. (2026). *Adaptive LLM-Generated Questionnaires for Suicide Risk Assessment: A Clinical Pilot in Greece*. 2nd NICE TEAS Europe, University of Thessaly.  
OSF registration: [https://doi.org/10.17605/osf.io/vcjrm](https://doi.org/10.17605/osf.io/vcjrm)  
Publisher / PDF link: _forthcoming_

```bibtex
@inproceedings{georgiou2026adaptive,
  title     = {Adaptive LLM-Generated Questionnaires for Suicide Risk Assessment: A Clinical Pilot in Greece},
  author    = {Georgiou, Dimitrios and Makrigiannis, Akis and Gerogiannis, Vassilis C. and Kanavos, Andreas},
  booktitle = {2nd NICE TEAS Europe},
  year      = {2026},
  address   = {University of Thessaly},
  note      = {OSF: https://doi.org/10.17605/osf.io/vcjrm; publisher DOI forthcoming}
}
```

You can also cite this repository via [`CITATION.cff`](CITATION.cff).

---

## License

Code is released under the **MIT License** — see [`LICENSE`](LICENSE).  
Clinical constraints and non-redistributable materials are described in [`NOTICE`](NOTICE).
