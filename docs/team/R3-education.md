# R3: UK education knowledge for Amin (2026-10-29)

Not legal advice. Items marked VERIFY need a written answer from the board or a solicitor before shipping.

## 1. Sources and licences

| Source | Terms found | Use for Amin |
|---|---|---|
| AQA specs, papers, mark schemes | All AQA material is copyright; written permission needed. Must not be reproduced on third-party websites. Permissions to registered centres cannot be passed on. **AQA states nobody may use AQA materials to train AI tools.** Contact copyright@aqa.org.uk. ([AQA copyright policy](https://www.aqa.org.uk/about-us/who-we-are/our-standards/copyright-and-intellectual-property-policy), [centres](https://www.aqa.org.uk/about-us/who-we-are/our-standards/copyright-and-intellectual-property-policy/copyright-policy-for-centres), [MAT policy](https://filestore.aqa.org.uk/admin/library/AQA-MAT-USE-POLICY.PDF)) | Do not train on it. Do not ship it inside the app. Ask for a written commercial licence. |
| Pearson Edexcel | All published material is copyright; must not be copied or made available electronically without permission. Some papers withheld due to third-party content. Contact copyrightPQS@pearson.com. ([Pearson policy](https://qualifications.pearson.com/en/support/support-topics/exams/past-papers/pearson-copyright-policy.html)) | Same as AQA. |
| Oak National Academy | Open Government Licence v3.0 (commercial use and adaptation allowed, attribution required), **except third-party assets**. Free API plus bulk JSON per subject; needs an API key. ([API terms](https://open-api.thenational.academy/docs/about-oaks-api/terms), [bulk](https://open-api.thenational.academy/bulk-download), [licensing guide](https://support.thenational.academy/a-guide-to-our-website-licensing)) | **Best legal core.** Ingest text only, drop third-party assets, keep per-lesson attribution. VERIFY API-key terms on redistribution and that it covers KS4 by board (Oak has board-specific KS4 programmes). Oak is KS1-4 only; no A level. |
| OpenStax | CC BY 4.0 (commercial allowed with attribution). VERIFY per book. | A level / university-level bio, chem, physics, maths, economics. Not UK-board-aligned; map by topic. |
| Wikipedia | CC BY-SA 4.0 (share-alike, attribution). | Retrieve and cite as an index with attribution. Keep it a separate, labelled pack to limit share-alike spread. |
| HF datasets of UK curriculum Q&A | Not verified. I did not find a reliable commercially licensed one; scraped board-paper sets are probably infringing. | Do not use unless licence is explicit (CC BY / Apache / OGL) and provenance is clean. |

**Owner-downloaded copies.** The user's own personal copy for private study is a different case from a commercial product. If the product includes a feature "import your own PDFs" (existing documents pipeline), the owner indexes their lawful copies locally, and the vendor ships none. That fits ADR-015 and is the lowest-risk route. AQA's AI-training ban means even user-supplied AQA material must be retrieval-only, never training data. VERIFY whether a consumer's local indexing counts as permitted use.

## 2. Architecture

**Retrieve, not fine-tune, for facts.** Build a "knowledge pack": chunks tagged `{board, spec_code, subject, level, topic, source, licence, url}`, in the existing local index. Answers cite board, spec code and topic. Packs are versioned, deletable, and per-source licensed.
- Pack A (shippable): Oak lessons (OGL), OpenStax, Wikipedia, plus your own written spec-point summaries (facts and topic lists are not copyrightable expression; own words only; no verbatim spec text). VERIFY.
- Pack B (user-imported): the owner's own downloaded specs, papers and mark schemes, indexed locally only.
- Retrieval: bilingual-safe embedding model (licence check), hybrid BM25 + dense, rerank, spec-code metadata filter chosen from the user's stated board and subject.

**Train (behaviour, using own-written or licensed synthetic data):** exam-style explanation, command-word handling ("state", "explain", "evaluate"), mark-allocation awareness (answer length matched to marks), worked-solution format, refusal to invent spec content when retrieval is empty, correct citation format. Generate training data from Pack A with a licensed teacher model, and check the teacher's terms. Never train on AQA/Pearson text.

## 3. Coverage map (verify codes on the board site before use)

| Subject | AQA | Pearson Edexcel |
|---|---|---|
| GCSE Biology | 8461 | 1BI0 |
| GCSE Chemistry | 8462 | 1CH0 |
| GCSE Physics | 8463 | 1PH0 |
| GCSE Combined Science | 8464 | 1SC0 |
| GCSE Maths | 8300 | 1MA1 |
| GCSE English Language | 8700 | 1EN0 |
| GCSE English Literature | 8702 | 1ET0 |
| GCSE History | 8145 | 1HI0 |
| GCSE Geography | 8035 | 1GA0 (A) / 1GB0 (B) |
| GCSE Computer Science | 8525 | (Edexcel offers 1CP2) |
| GCSE Business | 8132 | 1BS0 |
| GCSE Religious Studies | 8062 | 1RA0 etc. |
| A level Biology | 7402 | 9BN0 (Bio A) / 9BI0 (B) |
| A level Chemistry | 7405 | 9CH0 |
| A level Physics | 7408 | 9PH0 |
| A level Maths | 7357 | 9MA0 |
| A level Further Maths | 7367 | 9FM0 |
| A level English Lit | 7712 (A) / 7717 (B) | 9ET0 |
| A level History | 7042 | 9HI0 |
| A level Economics | 7136 | 9EC0 |
| A level Psychology | 7182 | 9PS0 |
| A level Computer Science | 7517 | n/a |

Other subjects (languages, art, DT, PE, sociology, etc.) follow the same pattern. Fetch each from the board's qualification page (AQA: aqa.org.uk/subjects/<subject>; Pearson: qualifications.pearson.com, per qualification "Teaching and learning materials"), saving the spec PDF locally. For the shipped pack, extract only spec codes, topic hierarchy titles and own-worded summaries. Codes above are from memory; VERIFY each one.

## 4. Evaluation

- Build a held-out set: for each board/subject, 30-50 exam-style questions **written by you or a hired teacher** (not copied from papers), with answer keys and mark-scheme-style marking points, plus topic and spec-code tags.
- Contamination control: hash and n-gram-dedupe the eval set against every training and retrieval document (Oak, Wikipedia, synthetic data). Eval authors must not see training data. Freeze the eval set, version it, and never use it for DPO or prompt tuning.
- Metrics: answer correctness vs key (teacher-model or human grading, calibrated on a sample), citation accuracy (spec code and topic match), abstention when the pack lacks content, and a no-retrieval baseline to prove retrieval adds value.
- Also test the user-imported path (Pack B) on a few of your own downloaded papers, locally only, and never in the shipped repo.

## Next actions
1. Email both boards for a written commercial licence (retrieval and AI use). AQA currently prohibits AI training.
2. Pull the Oak bulk JSON and audit third-party assets.
3. Write the own-words spec-point pack.
