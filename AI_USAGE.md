# AI usage

## Tools
- **Claude Code** (desktop app), model **Claude Opus 5.5**: read the brief and the TypeSafe docs, proposed the architecture, and drafted the code, test cases and docs, which I then reviewed.
- **Jev `jev-1.13.0`**: the decision model itself (not a coding aid).
- **Claude Haiku**: only in the optional, labelled post-decision letter and reviewer summary (`--with-llm`).

## By part
| Part | What I asked AI for | Accepted / changed / rejected, and why |
|---|---|---|
| Architecture | Read the Jev docs (`llms.txt`, primitives, confidence, jev-1.13 jaggedness, errors) and propose a design | **Accepted** "Jev judges, code decides", one request per grievance, the pinned model, and a Noul per project (avoids Choice option-order bias). **Changed:** the LLM is kept out of the decision path entirely, including no translation before Jev. Every choice is logged in `engineering_decision.md` (ED-001…). |
| Jev question design | Draft the Nouls and the Score, with criteria for boundary cases | **Changed:** sea_sh asked once for both the issue and the flag (ED-017). Reprisal and threat-to-life split into two literal questions each (ED-018). `other` moved from a Noul into code (ED-014). Criteria rewritten where Jev read them literally (see decision.md). |
| Policy code | P1–P8 as pure functions, fail-safe paths | **Accepted** the structure. **Rejected** a CLI option that trimmed `audit.thresholds` from single-case output, because the brief says fields must not be removed. |
| Test set | Draft hard cases by category (negation, injection, buried signal, euphemism, two projects, non-English, OCR junk) | **Checked every label by hand against P1–P8.** Where the label is a genuine judgment call, the field is either unscored or lists acceptable alternatives, with a note explaining why (e.g. T-021, T-029). |
| Eval script | Per-field accuracy, flag P/R, review rate, ±0.1 sweep | **Accepted.** I added the "missed safety cases" metric (an expected safety flag that ended up auto-routed), because that is the number that matters most. |
| Docs | README, the decision log, this file | Edited for accuracy against the code and the real eval output. |

## One thing AI got wrong
The first `config/thresholds.yaml` used keys `yes`, `no` and `on`. PyYAML follows YAML 1.1, which reads those as **booleans**, so `{yes: 0.7, no: 0.3}` loaded as `{True: 0.7, False: 0.3}`. **How I noticed:** the strict Pydantic config model (`extra="forbid"`) refused to load the file, and every test errored at collection. **What I did:** renamed the keys to `yes_at`, `no_at` and `flag_at`, and logged it as ED-016. Without strict config validation, this would have been a silent mis-thresholding bug.

## Verification
- **Code:** read every function. `pytest` runs 25 offline tests with synthetic Jev answers (all P1–P8 rules, routing order, floors, fail-safes, the 429/529 retry exhaustion audit, and that the `Action` type cannot express close/reject). I also checked the SDK's real signatures and error classes in the installed package before writing the client, rather than trusting generated code.
- **Eval harness:** smoke-tested with a fake Jev that returns constant answers. It must score badly, and it did, which shows the metrics aren't vacuous.
- **Test cases:** every expected label was re-derived by hand from the policy text. Cases where I disagreed with the draft were relabelled or left unscored, with a note.
- **Jev questions:** judged on real probabilities from the eval runs, not on how the wording looks (see decision.md).
