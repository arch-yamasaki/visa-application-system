# Blind Single-Case Extraction Prompt

You are extracting structured data for one Japanese immigration application case.

## Hard Rules

- Do not open, read, search, list, or infer from any `expected/` directory or any `*.golden.json` file.
- Do not use previously generated answers as source material.
- Use only the files listed in this run packet and the allowed reference files.
- Write outputs only under the run packet `generated/` directory.
- If a value is not present in the allowed input documents, leave it empty or `null` and add it to `review.json` as a missing item.
- Do not guess personal information.
- Do not log full personal values to chat. Keep sensitive values inside output JSON files only.

## Allowed Inputs

- `scenario.json`
- `document_manifest.blind.json`
- Files under `documents/`
- `allowed_reference_paths.txt`
- `output_contract.md`

## Forbidden Inputs

- `visa-eval/test_cases_from_raw/**/expected/**`
- Any file matching `*.golden.json`
- Any previous `generated/` output from another blind run
- `rasens-autofill/extension/application_data.json` if it contains real-case data
- Submitted application PDFs (`submitted_application_pdf`): these are used only as golden answer sources, not as AI extraction inputs

## Required Outputs

Write these files:

- `generated/case_data.json`
- `generated/review.json`
- `generated/run_notes.md`

Do not write `generated/application_data.json` manually. It should be generated deterministically from `case_data.json` using:

```bash
python3 rasens-autofill/scripts/build_application_data.py \
  <run_dir>/generated/case_data.json \
  rasens-autofill/data/mappings/rasens_offer_mapping.json \
  <run_dir>/generated/application_data.json
```

## Extraction Priorities

1. Applicant identity, passport, birth, nationality, sex, marital status, occupation.
2. Immigration history, prior COE applications, criminal record, deportation/departure order.
3. Family and relatives/cohabitants in Japan.
4. Education, major, graduation date, transcript subjects if visible.
5. Employment history and qualifications.
6. Employer/company information.
7. Employment terms: job title, duties, salary, period, workplace.
8. `application.activity_details` suitable for 技術・人文知識・国際業務 review.
9. Review findings: missing items, weak evidence, inconsistencies, human-review reasons.

## Review Policy

Use `needs_review` whenever evidence is missing, OCR/text extraction is weak, or a legal/practical judgment is required.

For 技術・人文知識・国際業務, explicitly check:

- Whether job duties connect to education, major, work history, or transcript subjects.
- Whether the duties might look like simple labor.
- Whether activity details are specific enough for human review.
- Whether documents are missing or inconsistent.

