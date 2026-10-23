# Engineering decision log

> **Append-only.** Every change and design decision gets logged here, newest at the bottom. Nothing in this file is ever deleted or rewritten. If a decision is reversed, a new entry says so, points to the old one, and explains why. The old entry stays as it was.
>
> Each entry records what was chosen, what it was chosen over, why, and the trade-offs accepted.

Format:

```
## ED-NNN · YYYY-MM-DD · <title>
Status: accepted | superseded by ED-XXX | revisited in ED-XXX
Context: what forced the decision
Decision: what we chose (A)
Alternatives: what we did not choose (B, C)
Why A: reasons A wins here
Trade-offs: what A costs us / what we gave up
```

---

## ED-001 · 2026-10-22 · Language: Python
Status: accepted
Context: The brief allows Python or TypeScript. TypeSafe ships official SDKs for both.
Decision: Python 3.13+ with the official `typesafe-sdk` (pinned to 0.7.5).
Alternatives: TypeScript with `@typesafe-ai/sdk`.
Why A: Pydantic gives typed input, output and config validation in a few lines. The eval and threshold sweep (precision/recall, sweeps over cached answers) are fast to write in Python. The reviewers can run it with just `pip`. The TS SDK infers answer types better, but that matters less here than validation and eval.
Trade-offs: No compile-time inference of answer types from questions. We get that safety at runtime through Pydantic and unit tests instead.

## ED-002 · 2026-10-22 · Pin the model version, not the alias
Status: accepted
Context: `jev-latest` currently points to `jev-1.13.0`, and `jev-preview` to `jev-1.14.0`. The docs say an alias moves when a new release ships, so answers can change with no change in our code.
Decision: Send `jev-1.13.0` explicitly (configurable in `config/thresholds.yaml`). Record `response.model` (the version that actually answered) in every audit block.
Alternatives: `jev-latest` (always newest stable), `jev-1.14.0` (newest preview).
Why A: Thresholds are tuned against one model's calibration. A silent model change would make the thresholds and the eval numbers stale without anyone noticing. P8 also requires the exact version in the audit. 1.13 is also the version with a published jaggedness (known failure modes) page, which we design against.
Trade-offs: We don't get 1.14 improvements automatically. Upgrading is a deliberate step: change the pin, re-run the eval, re-check the thresholds, then log a new ED entry.

## ED-003 · 2026-10-22 · Jev for judgment, code for everything else
Status: accepted
Context: The brief requires Jev as the core decision engine, and no LLM output may change the decision. The Jev docs say to keep arithmetic, dates and multi-step logic in code.
Decision: Jev only answers narrow semantic questions as probabilities. Code turns probabilities into booleans (thresholds) and applies P1 to P8 as pure functions. The decision boundary, split by component:
- Code: input validation, empty and junk detection, filing window and dates, eligibility status, urgency floors, routing order, also_notify, redaction, action, review_reasons, audit.
- Jev: project match, harm alleged, info-request-only, the 8 issue labels, the 4 safety flags, base urgency, injection detection, coherence, English or not.
- LLM: nothing in the decision path (see ED-010).
Alternatives: (B) Ask Jev for higher-level judgments directly, e.g. "which unit should handle this" or "is this eligible". (C) Use an LLM to produce the whole triage JSON.
Why A: Policy rules are deterministic and auditable. A reviewer can trace any field to a probability plus a threshold plus a rule. Changing a rule live is a one-line code change, not prompt tuning. B hides several judgments inside one question, which the Jev docs warn against, and makes routing order dependent on the model. C breaks the brief's rule outright.
Trade-offs: More questions per request (about 25), which is cheap since they run in parallel and cost only input tokens. More code to maintain. Policy bugs are now our bugs, so they need unit tests.

## ED-004 · 2026-10-22 · One Jev request per grievance (speculative fan-out)
Status: accepted
Context: Questions in one request are evaluated in parallel and independently. The docs show batching 13 questions as 12x cheaper and 10x faster than 13 calls, with the same answers.
Decision: Send all questions in one `system_one` call per grievance, including ones whose answers only matter sometimes (e.g. issue labels for an ineligible case).
Alternatives: (B) Cascade: ask eligibility first, then issues only if eligible. (C) One request per question.
Why A: Lowest latency and cost. The answers don't depend on each other. Even ineligible cases need issues and flags (Test 3 expects `community_health_safety` and also_notify `safeguards_environment`). It's also simpler to audit: one request, one response, one model version.
Trade-offs: We pay tokens for some unused answers, a negligible cost at $0.042/Mtok. The state is sent once with all questions, so it must fit in the 32k per-question context (see ED-012).

## ED-005 · 2026-10-22 · Project identification: one Noul per registry project
Status: accepted
Context: P1 needs the project, and "undetermined" when it can't be identified with confidence. The jev-1.13 docs list Choice option-order bias as a known failure mode ("leans toward the option that comes first").
Decision: Six independent Nouls, one per registry project ("Does `grievance_text` concern <name, location, sector>?"). Code takes the top one and requires it to clear a high threshold, with every other project below a low one. Otherwise the status is `undetermined`. If all are low, `no_matching_project`.
Alternatives: (B) One Choice over the 6 projects plus "none". (C) A Choice asked twice with the options reversed, using disagreement as an uncertainty signal.
Why A: Nouls have no option order, so the bias can't occur. Each project gets its own calibrated probability, so "matches two projects" and "matches none" are both visible directly instead of being squeezed into one distribution. Adding a project to the registry adds one question and leaves the others unchanged.
Trade-offs: The probabilities don't sum to 1, so we can't read a single "confidence". We gate on top vs runner-up in code instead. Six questions instead of one (cheap). For an input that mentions two projects (e.g. a road and a clinic), we route to undetermined and human review. That's the safe outcome, but it adds reviewer load.

## ED-006 · 2026-10-22 · Issues as 8 independent Nouls, not a multi-select Choice
Status: accepted
Context: P2 is multi-label. Choice picks exactly one option.
Decision: One Noul per issue label, each with `true`/`false` criteria spelling out the boundary cases.
Alternatives: (B) One Choice for the "primary issue" plus Nouls for secondary ones. (C) A Score per issue for severity.
Why A: Multi-label is a natural fit for independent yes/no probabilities. Each label gets its own threshold and its own precision/recall in the eval. There's no order bias.
Trade-offs: Labels can be inconsistent (e.g. `information_request` high together with a harm-type issue). Code resolves that: `info_access_desk` only gets the case when information_request is the only issue (P5 row 7).

## ED-007 · 2026-10-22 · Filing window and dates computed in code only
Status: accepted
Context: The jev-1.13 docs: "reads dates as text, not as ordered quantities... unreliable" for windows. P1 condition 3 is a date window.
Decision: The window check uses `received_at` from the input metadata and the registry's status and closing date: eligible if the project is active, or `received_at <= closing_date + 24 months`. Jev is never asked about dates.
Alternatives: Ask Jev "was this received within 24 months of closing".
Why A: This is exact arithmetic on structured data, so code is the right tool. The policy keys on the date the grievance was received, not on when the harm happened, so no date needs to be extracted from the text.
Trade-offs: If a complainant writes "this happened in 2021", that doesn't affect eligibility. That matches P1 as written. We note it in the README as an assumption.

## ED-008 · 2026-10-22 · Pydantic for input, output, config and audit
Status: accepted
Context: The output shape is fixed by the brief, and fields must not be renamed or removed. Bad input must not crash a batch.
Decision: Pydantic v2 models: `GrievanceIn`, `TriageOut` (with `action: Literal["auto_route","human_review"]`), `Thresholds` (loaded from YAML), and `Audit`.
Alternatives: (B) Plain dicts with manual checks. (C) dataclasses with jsonschema.
Why A: One source of truth for the schema. The type itself makes "close" or "reject" impossible to emit (a non-negotiable in the brief). Typos or out-of-range values in the thresholds file fail at startup. Invalid input records turn into a `human_review` output with reason `invalid_input` instead of an exception.
Trade-offs: An extra dependency, and validation is stricter than the brief (e.g. an unknown channel goes to review). We take that on purpose.

## ED-009 · 2026-10-22 · Threshold bands per decision, versioned in YAML
Status: accepted (values to be calibrated against the eval; changes get new entries)
Context: P6 asks us to choose and justify the thresholds. The Noul docs suggest 0.7 yes / 0.3 no with the middle band going to a person, and say to lower the yes threshold when missing a true yes is expensive (e.g. safety).
Decision: Asymmetric bands, by cost of error:
- Safety flags (sea_sh, reprisal_risk, threat_to_life): flag true at p >= 0.5. If 0.2 <= p < 0.5, the flag stays false but the case goes to human review with reason `uncertain_<flag>`.
- confidentiality_requested: true at p >= 0.5 (a false positive only redacts the name, which is cheap).
- Issues, harm_alleged, info_only: yes at >= 0.7, no at <= 0.3. In between means review.
- Project: top >= 0.7 and runner-up <= 0.3, otherwise undetermined.
- Urgency Score: confidence >= 0.5, otherwise review.
All values are in `config/thresholds.yaml` with a `version` string that goes into every audit block.
Alternatives: (B) One global threshold (e.g. 0.5 for everything). (C) Fit the thresholds tightly to the test set.
Why A: A missed safety case costs far more than a reviewer's minutes, so safety thresholds favour recall. A routine label error is recoverable, so we demand more confidence before auto-routing. B treats a dust complaint like an assault. C overfits to about 30 hand-written cases (the Noul docs warn about this).
Trade-offs: More human review on borderline safety language, i.e. more reviewer workload. The ±0.1 sweep in the eval will quantify this.

## ED-010 · 2026-10-22 · LLM only after the decision, labelled, optional
Status: accepted
Context: The brief: an LLM may be used, but no LLM output may change the triage decision, and any LLM output must be labelled.
Decision: The LLM (Anthropic Claude Haiku) runs only after `TriageOut` is final. It (1) drafts an acknowledgment letter to the complainant, and (2) gives the reviewer a short English summary, or a translation of non-English text. Both are stored under `llm_outputs` with `llm_generated: true` and the model name. Enabled with `--with-llm`. If `ANTHROPIC_API_KEY` is missing, the step is skipped. LLM test-case drafting happens at dev time only and is hand-checked.
Alternatives: (B) No LLM at all. (C) An LLM translating non-English input before Jev reads it.
Why A: It adds real reviewer and complainant value at no risk to the decision. B is safe but leaves the "could have" undone. C is rejected: a translation fed to Jev would shape the decision, which breaks the brief's rule. A mistranslation could also hide a safety signal.
Trade-offs: A second vendor and key, and extra latency when enabled. The letter must not reveal internal routing or identity details, which is handled in the prompt and checked in tests.

## ED-011 · 2026-10-22 · Non-English input: Jev reads the original, always human review
Status: accepted
Context: The Jev docs say English is the primary language and other languages are "handled but not equally well". The brief requires us to choose and justify our handling.
Decision: Detect language with a Jev Noul (`is_english`) plus a cheap code heuristic (share of ASCII letters). Jev still runs on the original text, so flags, urgency floors and routing still apply. The action is always `human_review` with reason `non_english_input`.
Alternatives: (B) Translate with an LLM, then triage. (C) Reject or skip non-English input.
Why A: Safety signals in other languages still get flagged and routed with the right urgency. A human still checks every decision, since our eval can't show recall on languages we didn't test. B breaks ED-010. C would deny service and goes against "may never close or reject".
Trade-offs: Every non-English grievance costs reviewer time, even routine ones. If non-English volume turns out to be high, this needs revisiting with a multilingual eval set.

## ED-012 · 2026-10-22 · Robustness: injection, junk input, long input, API failures
Status: accepted
Context: The jev-1.13 docs list adversarial content and large-state distraction as failure modes. The brief requires 429/529 handling and says empty or unreadable input means review.
Decision:
- The state is JSON (`{"grievance_text": ..., "channel": ...}`) and every question refers to `grievance_text` explicitly. A Noul `contains_instructions_to_system` sends the case to review with reason `possible_injection`.
- Code catches empty, whitespace-only or very short text, and OCR junk (a low share of alphabetic characters). A Jev Noul `text_is_coherent` acts as a second check. Either one gives reason `unreadable_input`.
- Text longer than a configured limit is truncated for Jev, and the case goes to review with reason `input_truncated`.
- 429/529 errors: the SDK's `RetryPolicy` with exponential backoff and jitter, honouring `retry-after`, with the statuses set explicitly to include 429 and 529. If retries run out, the output is `human_review` with reason `jev_unavailable` and route `grs_general`. The batch never stops and no grievance is lost.
Alternatives: (B) Crash the batch on API error. (C) Silently skip failed records.
Why A: B and C both lose grievances. A fail-safe that sends the case to a person keeps the "never miss a safety case" promise even when the model is down.
Trade-offs: An outage turns into a spike in reviewer load. That is the right failure direction for this domain.

## ED-013 · 2026-10-22 · Record and replay cache for Jev responses
Status: accepted
Context: The eval, the ±0.1 threshold sweeps and the live review all re-run the same inputs. decision.md needs reproducible numbers.
Decision: The Jev client saves raw responses to disk (`.jev_cache/`, keyed by a SHA-256 of model, state and questions). Modes: `live` (default), `record`, and `replay` (offline, fails if an entry is missing).
Alternatives: Always call the API, or mock Jev in the eval.
Why A: Threshold sweeps re-run instantly with no API cost, and the eval output can be reproduced exactly from committed cache files. The policy change in the live review is visible immediately. Mocks would make the eval meaningless.
Trade-offs: The cache can go stale when questions change. That's handled by hashing the question text into the key, so any wording change misses the cache. The cache is gitignored by default, except for the eval cache we choose to commit.

## ED-014 · 2026-10-22 · Issue label `other` is derived in code, not asked of Jev
Status: accepted
Context: P2 includes `other`. As a Noul, it would read "does this raise a concern that is none of the seven above". That is a double-hop, negated question, the "indirection" failure mode in the jev-1.13 docs.
Decision: `other` is added in code when no substantive issue (anything except `information_request`) clears its threshold and the status is not `not_applicable`.
Alternatives: (B) A Noul with criteria listing the other seven labels. (C) A Choice with an "other" option.
Why A: It's exact and costs nothing. It always agrees with the other labels by construction, so a case can't be both "other" and "pollution".
Trade-offs: `other` also fires when Jev was merely uncertain about a real label. That case is already sent to review through `uncertain_issue_*`, so a person sees it either way.

## ED-015 · 2026-10-22 · Our own retry loop for 429/529, SDK retries off
Status: accepted
Context: The SDK's default `RetryPolicy` already retries 429 and 5xx (including 529) with backoff and `retry-after`. But it doesn't report how many attempts were made, and the brief explicitly grades 429/529 handling.
Decision: `RetryPolicy(max_retries=0)` in the SDK. `jev_client.py` retries itself: up to 5 attempts on {408, 429, 500, 502, 503, 504, 529} and on connection/timeout errors, with exponential backoff (0.5s doubling, capped at 8s, ±25% jitter) and `retry-after` honoured. Attempts and statuses go into the audit (`jev_attempts`, `jev_statuses`). Other statuses (400/401/422) fail fast to `human_review`.
Alternatives: (B) Use the SDK default retry policy as-is.
Why A: The handling is visible, testable without a network (unit test simulates five 529s), and auditable. Reviewers can see in the output that a grievance needed retries.
Trade-offs: About 40 lines of our own code that duplicate SDK behaviour, so it needs its own tests and maintenance.

## ED-016 · 2026-10-22 · Bug caught: YAML 1.1 parses `yes`/`no`/`on` keys as booleans
Status: accepted (fix)
Context: The first `thresholds.yaml` used keys `yes`, `no` and `on`. PyYAML follows YAML 1.1, where these are booleans, so `{yes: 0.7}` loaded as `{True: 0.7}`. The strict Pydantic config model (`extra="forbid"`) refused to load it, so the bug surfaced at startup instead of silently mis-thresholding.
Decision: Rename the keys to `yes_at`, `no_at` and `flag_at`.
Alternatives: (B) Quote the keys (`"yes": 0.7`). (C) Switch to a YAML 1.2 parser (ruamel).
Why A: No quoting rule to remember during a live threshold change, and no new dependency. It also confirms the value of ED-008: without strict validation, every routine Noul would have crashed or defaulted at runtime.
Trade-offs: None worth noting.

## ED-017 · 2026-10-22 · sea_sh asked once; the issue label and the flag share one answer and one threshold
Status: accepted
Context: P2 has an issue `sea_sh` and P3 has a flag `sea_sh`. Two questions, or one question with two thresholds (issue 0.7, flag 0.5), could produce "flag true, issue missing".
Decision: One Noul, `issue_sea_sh`. Both the label and the flag use the safety band (`flag_at: 0.5`).
Alternatives: (B) Separate questions for each. (C) One question, read through each field's own threshold.
Why A: The two fields mean the same thing in the policy, so they must never disagree. The safety threshold applies because the cost of a miss is the same.
Trade-offs: The sea_sh issue label is more recall-heavy than the other labels. That's acceptable, because every sea_sh case goes to human review anyway.

## ED-018 · 2026-10-22 · threat_to_life and reprisal_risk are each two literal Nouls, OR-ed (max) in code
Status: accepted
Context: The jev-1.13 docs say Jev reads questions literally. "Retaliation" covers both feared future retaliation and retaliation that already happened (T-017: a son fired after his mother complained, with no fear stated). "Threat to life" covers both dangerous conditions (an open trench, a gas leak) and explicit threats of violence.
Decision: reprisal_risk = max(`flag_reprisal_feared`, `flag_reprisal_occurred`). threat_to_life = max(`flag_threat_to_life`, `flag_violent_threat`).
Alternatives: (B) A single Noul each, with broad criteria.
Why A: Each sub-question is a single, literal judgment. A combined question would make Jev weigh two conditions at once, and the docs say the resulting value "means less". The max keeps recall high. Every sub-probability is in the audit, so a reviewer can see which side fired.
Trade-offs: Two more questions (cheap). Using max raises false positives: any threat of violence counts as threat_to_life, even a vague one. Those go to review, and the precision cost shows in the eval.

## ED-019 · 2026-10-22 · Uncertain confidentiality request redacts the identity but does not force review
Status: accepted
Context: P6 lists the triggers for mandatory review, and confidentiality_requested is not one of them. A false "true" only hides a name. A false "false" could expose a complainant.
Decision: p >= 0.5 sets the flag (and redact_identity). 0.3 <= p < 0.5 leaves the flag false but still sets `redact_identity: true` ("protective redaction", visible in `audit.derived.confidentiality_state`). No review reason is added for it.
Alternatives: (B) Send uncertain confidentiality to review. (C) Ignore the middle band.
Why A: Redaction is cheap and reversible. Exposing someone isn't. Adding review load for a decision that redaction already makes safe would waste reviewer time.
Trade-offs: Some complainants who didn't ask for anonymity get redacted, which is mildly inconvenient for the project team.

## ED-020 · 2026-10-22 · Fail-safe output when Jev or the input fails
Status: accepted
Context: The brief: "may never close or reject a grievance", and empty or unreadable input means review.
Decision: `policy.fail_safe(reason)`: status `undetermined`, route `grs_general`, action `human_review`, urgency `priority` (10 days, not 30), `redact_identity: true` (we couldn't check for a confidentiality request), and reason codes `jev_unavailable` / `jev_http_<status>` / `invalid_input` / `unreadable_input`. Empty text skips the Jev call entirely. Junk text (OCR noise) is still sent, because a readable fragment might carry a safety signal.
Alternatives: (B) Raise an error and let the caller decide. (C) Default urgency to routine.
Why A: Every input produces a valid output that reaches a person. Priority is a cautious middle ground: we can't rule out a safety case, but promoting every outage to "urgent" would swamp reviewers.
Trade-offs: A real threat-to-life case that arrives during an outage gets 10 days instead of 24 hours until a person reads it. Mitigation: the reason `jev_unavailable` should be monitored and paged on in production (README).

## ED-021 · 2026-10-22 · Low-confidence urgency rounds up and goes to review
Status: accepted
Context: The urgency Score sometimes splits between adjacent levels (e.g. routine 0.45 / priority 0.40).
Decision: If the Score's `confidence` < 0.5, take the most severe level that has at least 0.25 probability, and add `uncertain_urgency`. Floors (P4) are applied after that.
Alternatives: (B) Use the argmax level. (C) Use the expected value and round it.
Why A: Overstating urgency only costs a faster response. Understating it breaks the response promise. The jev docs also warn against interpolating Score levels numerically (C).
Trade-offs: More `priority` than strictly necessary on ambiguous routine cases.

## ED-022 · 2026-10-22 · Test set authored as Python source (`data/make_testset.py`) that writes JSONL
Status: accepted
Context: The brief asks for a test set of at least 25 cases with expected decisions, including acceptable alternatives (e.g. "priority (routine acceptable)").
Decision: The cases live in a readable Python file with helpers (`flags()`, `case()`), a note per case explaining the label, and tags (safety, negation, injection, non_english...). It generates `data/testset.jsonl` (34 cases: 3 brief samples + 31 own). Expected values can be a list of acceptable values, and `*_include` keys allow subset checks where the brief's answer is "includes X".
Alternatives: (B) Hand-edit JSONL directly.
Why A: Reviewers read and challenge labels much faster in the Python file. Notes record why a label is what it is, and that reasoning is what the live review probes.
Trade-offs: Two artifacts (the source and the generated file). The JSONL is committed so the eval runs without the generator.

## ED-023 · 2026-10-22 · Threshold sweep replays cached Jev answers
Status: accepted
Context: decision.md asks what happens to missed safety cases and reviewer workload if the main threshold moves by 0.1 either way.
Decision: `eval/run_eval.py` runs the baseline (calling Jev and recording responses), then re-runs the policy at safety ±0.1 and routine ±0.1 with `--cache replay`. Thresholds aren't part of the cache key, so no extra API calls are made.
Alternatives: (B) Re-call Jev for each variant.
Why A: Same answers, so the only variable is the threshold. That is the controlled comparison the question asks for, and it's free and instant.
Trade-offs: None. Jev answers don't depend on our thresholds.

## ED-024 · 2026-10-22 · Commit the Jev response cache for the test set
Status: accepted
Context: Reviewers clone the repo fresh, and the eval numbers in decision.md must be reproducible. Reviewers may not want to spend their own key re-running 34 cases.
Decision: `.jev_cache/` (raw Jev responses for the test set, keyed by model + state + questions) is committed. `--cache replay` re-creates the committed eval output exactly, with no API key.
Alternatives: (B) Gitignore the cache and ask reviewers to run live.
Why A: Reproducible evidence. The ±0.1 sweep and any live threshold change can be shown offline in seconds. The responses contain only our own synthetic test grievances, so there is nothing sensitive or secret.
Trade-offs: The repo grows by roughly 34 small JSON files. Any question wording change invalidates the matching entries, which then need a live re-run (by design, see ED-013).

## ED-025 · 2026-10-22 · Secrets via a gitignored `.env` file, loaded with python-dotenv
Status: accepted
Context: The brief says to read the key from `TYPESAFE_API_KEY` and never commit it. Setting environment variables on Windows (setx, PowerShell profile) is fiddly, and the reviewers will clone the repo fresh.
Decision: `triage/env.py` loads `<repo>/.env` at CLI and eval start-up with `override=False`, so real environment variables always win. `.env` is gitignored, and `.env.example` (no values) is committed as a template.
Alternatives: (B) Environment variables only (`export` / `setx`). (C) A secrets manager or keyring.
Why A: Works the same on Windows, macOS and Linux with one file. The brief's contract (read `TYPESAFE_API_KEY` from the environment) still holds, because dotenv just populates the environment. C is overkill for a CLI take-home.
Trade-offs: A new dependency (python-dotenv). The key sits in a plaintext file on disk, so it must stay out of git, which `git check-ignore` confirms.

## ED-026 · 2026-10-22 · Project question wording: tried v2 and v3, reverted to v1
Status: accepted. Revisits ED-005 (still one Noul per project).
Context: Run 1 (first live eval, `eval/results/runs/run1_*`). T-006 ("our land in Tamsa was taken for the road widening") gave P-1041 = 0.28, so the case became ineligible / no_matching_project.
Decision: Tried two rewrites, measured on all 26 project-labelled cases:
- v2 put a plain description of the works inside the question ("...project, which covers road rehabilitation and widening, highway works, quarry trucks..."). Sample 2 went 0.89 → 0.67 and T-014 0.80 → 0.53. 15 cases fell below 0.7 and became undetermined. T-006 barely moved (0.31).
- v3 kept a short question and put the works in the criteria as "names this project, OR describes any of its works. Either one is enough." This was better than v2 on some cases (sample 2: 0.78) but worse than v1 overall (T-002: 0.84 → 0.55, T-022: 0.55 → 0.27).
- Kept v1. The `works` field stays in the registry but is not used in questions.
Alternatives: Keep iterating the wording. Switch to a Choice.
Why A: v1 had the highest true-project probability on 22 of 26 cases. The key observation held across all three wordings: **the runner-up project was ≤ 0.05 in every case**, except T-011, which really does mention two projects (0.82 / 0.53). Wording moves the absolute level but never the ranking. That points to changing the decision rule (ED-030), not more wording churn, which risks overfitting 26 cases.
Trade-offs: T-006 stays a miss (0.28). It fails safe: ineligible / no_matching_project goes to human review and grs_general.

## ED-027 · 2026-10-22 · Removed the `info_request_only` Noul; not_applicable = asks for information AND no harm alleged
Status: accepted. Supersedes the info-only part of ED-003 and ED-009.
Context: Run 1, T-030: "I asked the project office for the impact report three times and nobody answers. Is the report public? Where can I read it?" gave `info_request_only` = 0.19 (harm_alleged = 0.04), so the case was not treated as an information request. Jev read "only... without complaining about any problem" literally: "nobody answers" is a complaint. T-023 gave 0.48 (uncertain). This is the literal-reading failure mode from the jev-1.13 docs.
Decision: Drop the question and derive in code: `issue_information_request` ≥ 0.7 AND `harm_alleged` ≤ 0.3 → not_applicable → info_access_desk. The `info_only` threshold block was removed (thresholds v .2).
Alternatives: (B) Reword the "only" question with more criteria.
Why A: Two plain facts Jev already answers well, combined in code, instead of one question that hides a conjunction and a negation. Run 4: T-030 0.98 / 0.04 → not_applicable. T-023 0.97 / 0.05 → not_applicable. T-009 (praise) 0.02 / 0.01 → still ineligible / no_harm_alleged.
Trade-offs: One fewer question. A message that asks for information and also hints at a minor grievance with harm in the middle band now goes to review (uncertain_harm_alleged) rather than the info desk.

## ED-028 · 2026-10-22 · threat_to_life sub-questions narrowed (revisits ED-018)
Status: accepted. Revisits ED-018 (still two Nouls, max in code).
Context: Run 1 violated a non-negotiable. Brief Sample 2 routed to protection_unit (immediate) instead of sea_specialist, because `flag_violent_threat` ("threatened with violence or physically attacked") = 0.77 on "one woman was pushed into his office". The same thing happened on T-016 (an arm grabbed: 0.82) and T-027 (a threat to demolish a house: 0.73). `flag_threat_to_life` also fired on T-004 (no drinking water on site: 0.59). threat_to_life precision was 0.57.
Decision: `flag_violent_threat` now asks about threats to kill or seriously hurt, or beatings and weapon attacks, with pushing, grabbing, touching and threats to a job or home listed under false. `flag_threat_to_life` now asks about a present physical danger (pits, gas, collapse, electricity, near-misses), with harassment, working conditions and pollution listed under false.
Alternatives: (B) Raise the threat_to_life threshold to 0.8. (C) Drop violent_threat.
Why A: The fault was the question's scope, not calibration: Jev was right that the woman was physically pushed. B would trade recall on real threats for the same over-broad question. C would lose T-014, where after the change `flag_threat_to_life` = 0.15 but `flag_violent_threat` = 0.99 (beaten, threatened with death), which is exactly why we keep two sub-questions. Run 4: Sample 2 0.07 / 0.04 → sea_specialist, urgent. T-016 0.13 / 0.04. T-027 0.06 / 0.04. True cases T-013 0.98, T-018 0.98, T-019 0.97 unchanged. threat_to_life precision 1.00, recall 1.00.
Trade-offs: Fewer threat flags on physical-but-not-serious contact. Those cases still go to review through sea_sh or reprisal when present. A case of pure assault without "serious" wording would rely on violent_threat's criteria.

## ED-029 · 2026-10-22 · Low-confidence urgency: take the higher of the top two levels (revisits ED-021)
Status: accepted. Revisits ED-021.
Context: ED-021's rule ("most severe level with ≥ 0.25") pushed T-002 (fraud; probabilities 0.34 / 0.39 / 0.27) up to urgent, two steps above Jev's most likely level.
Decision: When the Score's confidence is < 0.5, use the more severe of the two most likely levels, and add `uncertain_urgency` (review).
Alternatives: (B) Keep the ≥ 0.25 rule. (C) Use ceil(expected score).
Why A: Still conservative (it never goes below argmax), but it moves at most to the runner-up level Jev actually considered. It doesn't interpolate on Score levels, which the docs warn against for C. T-002 → priority. A regression test pins the real run-1 answer.
Trade-offs: A 3-way split that includes "immediate" at < 2nd place isn't escalated. The review flag still sends it to a person.

## ED-030 · 2026-10-22 · Project match threshold 0.7 → 0.5, gated on separation from the runner-up
Status: accepted (thresholds `th-2026-10-22.3`).
Context: ED-026 showed that the absolute level of the true-project Noul varies with wording (0.53–0.99), while runner-ups stay ≤ 0.05.
Decision: match = top ≥ 0.5 AND runner-up ≤ 0.3. A top between 0.3 and 0.5 means undetermined, and ≤ 0.3 means no_matching_project.
Alternatives: (B) Keep 0.7. (C) Use a ratio of top to runner-up only.
Why A: P1's "cannot be identified with confidence" means "not sure which registry project". A 0.5 top with every other project at 0.01–0.05 is unambiguous about which. The runner-up cap keeps real two-project cases (T-011) undetermined. Run 4 vs run 3 (same thresholds, other wording): all fields correct 0.50 → 0.85, eligibility.status 0.97, project_id 0.96. Thresholds were chosen from the separation structure seen over three wordings (~96 observations), not to make specific cases pass. The routine ±0.1 sweep (which also moves `match`) changes all-fields accuracy by at most 0.03.
Trade-offs: A case that only vaguely suggests one project (top 0.5, nothing else) is treated as identified. If it's actually unrelated, eligibility is wrong, but routing still follows issue labels, and ineligible or undetermined cases are reviewed anyway.

## ED-031 · 2026-10-22 · Stop tuning at run 4; archive every run
Status: accepted
Context: Each live eval costs about $0.004 and 15 seconds, so endless iteration is cheap. With 34 cases, every further change risks fitting the test set.
Decision: Stop at run 4. Every run is archived in `eval/results/runs/runN_<thresholds_version>/` (report, metrics, outputs, and a snapshot of `questions.py` where the questions changed), so decision.md can cite real before/after numbers. The remaining 5 failures are documented as known gaps, and all of them fail safe (review, not a wrong auto-route): T-002 and T-004 have uncertain urgency, T-006 is a project miss, T-015 is a reprisal false positive, and T-020 has an extra community-health label.
Alternatives: Keep tuning until 100%.
Why A: The unseen inputs in the live review are what count, and overfitting would hurt there. The safety metrics (0 missed safety cases, recall 1.00 on every flag, 0 under-review) are already where they must be.
Trade-offs: 3 of 9 routine cases still go to review (over-review). That is the next thing to improve, ideally with more data rather than more wording changes.

## ED-032 · 2026-10-22 · Date-window probe kept as evidence (eval/probes/date_probe.py)
Status: accepted
Context: decision.md asks for raw Jev output for a limitation that shaped the design. ED-007 kept dates in code, based on the docs.
Decision: A small probe asks Jev the filing-window question directly over 6 date pairs with known answers. The output is committed (`eval/results/date_probe.jsonl`).
Result: Jev was right on the easy cases but **confidently wrong at the boundary**: received 2024-04-01 for closing 2022-03-31 (one day late) gave p(in window) = 0.89. A 0.89 would pass any threshold we would use.
Why: It turns a design rule from the docs into evidence from our own runs.
Trade-offs: 6 extra API calls (negligible).

## ED-033 · 2026-10-22 · Bump policy_version to `mdb-grs-p1-p8/2026-10-22.2`
Status: accepted (fix)
Context: ED-027 changed policy logic (not_applicable is now derived in code), but `policy_version` in `config/thresholds.yaml` still said `.1`. Every audit block written since run 2 carried the wrong policy version. Spotted while reading Test 1's raw output.
Decision: Bump it to `.2`. From now on, any change to `triage/policy.py` that can change an output also bumps `policy_version`, in the same change.
Alternatives: (B) Derive policy_version automatically from a hash of policy.py.
Why A: A human-readable version is what auditors and complainants will quote. A hash changes on comment edits too. A hash-based check in CI would be a sensible later addition.
Trade-offs: It depends on discipline. The archived run-2…run-4 outputs keep the stale `.1` label, and this entry is the correction record.

## ED-034 · 2026-10-22 · FastAPI service as a thin layer over the same pipeline
Status: accepted
Context: The user asked to expose triage over HTTP and to drive it from a live UI. The brief says a UI and deployment are "not needed", so this is additive. The CLI remains the documented way to run it.
Decision: `api/main.py`: `POST /triage`, `POST /triage/batch` (≤ 200), `GET /health`, `/questions`, `/config`, `/samples`, `POST /admin/reload-thresholds`. One shared `JevClient` (with concurrency limit and cache) is created in the app lifespan. The request body is a plain dict, not `GrievanceIn`, so invalid input still goes through the pipeline and comes back as `human_review` / `invalid_input` instead of a FastAPI 422. If the key is missing, the API starts anyway, `/health` reports `degraded` with the reason, and `/triage` returns 503.
Alternatives: (B) Let FastAPI validate the body with `GrievanceIn` (422 on bad input). (C) Re-implement the decision flow in the API.
Why A: B would make the HTTP path behave differently from the CLI and batch paths, and a 422 is a rejection, which the brief forbids in spirit ("may never close or reject"). C would duplicate policy and invite drift. The reload endpoint supports the live-review task "change a threshold live" without a restart, and invalid YAML is refused while the old thresholds stay active.
Trade-offs: The OpenAPI schema shows the request body as a free-form object rather than typed fields (an example is provided). No auth on the admin endpoint, which is acceptable for a local tool and must be added before any real deployment.

## ED-035 · 2026-10-22 · Streamlit UI that only talks to the API
Status: accepted
Context: Live runs during the review, showing the raw Jev answers the reviewers will ask about.
Decision: `ui/app.py` uses only HTTP calls to `API_URL`. It has a single-grievance tab (pick a labelled case or write a new one, then see the decision, expected vs got, and every Noul on a fixed 0–1 scale with the threshold lines from the audit block, plus the urgency distribution and the full JSON) and a batch tab (full test set or uploaded JSONL, with review rate and match rate).
Alternatives: (B) Have the UI import `triage` directly. (C) Use Streamlit's default auto-scaled bar charts.
Why A: The UI exercises the same path an integrator would use, and the API and UI can be deployed separately. C was tried first and was misleading: with auto-scaling, safety probabilities of 0.01–0.09 filled the whole chart and looked alarming. A fixed 0–1 axis plus threshold lines shows at a glance whether a value is clear, uncertain or flagged.
Trade-offs: A second process to run. The expected-vs-got comparison is re-implemented in the UI (about 30 lines mirroring `eval/run_eval.field_checks`), a small duplication accepted to keep the UI independent of the package.

## ED-036 · 2026-10-22 · Correction: the question count is 23, not "about 25"
Status: accepted (correction)
Context: ED-003 and the early README said "about 25 questions", and an explanation to the user said "24 Nouls + 1 Score". `/health` reports `n_questions: 23`. 6 projects + harm + 7 issues + 4 safety sub-questions + confidentiality + 3 robustness = 22 Nouls, plus 1 urgency Score. (`info_request_only` was removed in ED-027.)
Decision: README and decision.md now say 23. Earlier log entries are left as written (append-only), and this entry is the correction.
Trade-offs: None.

## ED-037 · 2026-10-22 · Run the dev servers directly, not through the preview launcher
Status: accepted
Context: The desktop preview tool reads `.claude/launch.json` from the other project in this session (`C:\ffp-bgv`), not this repo.
Decision: Started uvicorn (8000) and Streamlit (8501) as background processes and opened the UI in the browser pane by URL for verification. A `.claude/launch.json` with `api` and `ui` configurations is still added to this repo for future sessions rooted here.
Alternatives: (B) Add our configurations to the other project's launch file.
Why A: It doesn't modify an unrelated repository.
Trade-offs: The servers have to be stopped by hand.

## ED-038 · 2026-10-22 · README diagrams as Mermaid, screenshots via Playwright on local Edge
Status: accepted
Context: The user asked for a README that explains the architecture and the Jev question design visually, renders on GitHub, and shows the GUI.
Decision: 8 Mermaid diagrams (pipeline, who-decides, HTTP sequence, question mindmap, decomposition, threshold bands, P5 routing, API/UI topology), which GitHub renders natively from text. Three UI screenshots in `docs/img/`, generated by `tools/screenshots.py` (Playwright with `channel="msedge"`, so no browser download) against the API in `TRIAGE_CACHE=replay` mode, so the images match recorded answers. To make screenshots scriptable, the UI accepts deep links `?case=<id>&run=1`. Every diagram was parsed and rendered with mermaid 11 in a real browser before committing.
Alternatives: (B) Exported PNG/SVG diagrams. (C) ASCII art (the previous README).
Why A: Mermaid diagrams stay in sync with edits (they are text in the README, diffable in PRs) and GitHub renders them without image files. Screenshots of the real UI show what the reviewers will see in the live session.
Issues found while checking: the first "who decides" diagram (subgraphs with inner direction) collapsed to 1169×52 px, and the routing tree was 1514–2082 px tall because all leaves converged on one note node. Rebuilt as three multi-line boxes and a convergence-free staircase with short labels. Headless Edge `--screenshot` captured Streamlit before its websocket render (blank skeleton), so Playwright waits for the result text instead.
Trade-offs: Playwright is a dev-only dependency (not in pyproject runtime deps). Mermaid styling differs slightly between GitHub light and dark themes. Screenshots must be regenerated by hand when the UI changes.

## ED-039 · 2026-10-22 · README diagrams as committed PNG images (revisits ED-038)
Status: accepted. Revisits ED-038 (inline Mermaid).
Context: The user asked for the diagrams to exist as image files, saved in a folder and embedded in the README.
Decision: Each diagram lives as Mermaid source in `docs/diagrams/NN-name.mmd`. `tools/render_diagrams.py` renders them to `docs/img/diagrams/NN-name.png` with mermaid 11 in local Edge (Playwright) at 2x density on white. The README embeds the PNGs with `<img>` (centred, fixed display width), each with a link to its `.mmd` source.
Alternatives: (B) Keep inline Mermaid (ED-038). (C) Commit SVG instead of PNG.
Why A: The images look identical everywhere (GitHub light/dark, other Markdown viewers, PDF exports, IDE previews), whereas inline Mermaid renders only where Mermaid is supported and restyles in dark mode. The `.mmd` sources keep the diagrams editable and diffable. PNG over SVG because Mermaid SVGs use `<foreignObject>` HTML labels, which some viewers drop when the SVG is loaded via `<img>`, leaving empty boxes.
Issues found while rendering: (1) the first pass produced every image at 348 px, because Mermaid sizes its SVG to the container; fixed by setting width and height from the SVG viewBox. (2) The question-set mindmap overlapped a node onto the centre circle in two layouts (the mindmap engine is not deterministic). It was replaced with a top-down flowchart of six grouped boxes.
Trade-offs: Images must be regenerated (`python tools/render_diagrams.py`) after editing a `.mmd`. Binary PNGs (about 260 KB in total) are in git. PNGs have a white background, which shows as a white card in GitHub dark mode.

## ED-040 · 2026-10-22 · Plain-language project guide as a Word document
Status: accepted
Context: The user asked for a document explaining the whole project, with diagrams and intuitive explanations. Their standing preference is that "a document" means a .docx under docs/.
Decision: `docs/Jev_Grievance_Triage_Project_Guide.docx` (24 pages, A4), built by `tools/build_guide.js` (Node + docx). It is organised as a story: the problem, the core idea ("a fast reader and a strict clerk"), one grievance followed end to end, question design, thresholds as a traffic light, the rulebook, safety nets, the audit trail, testing and lessons, results, usage, and limits plus a glossary. It has 13 figures: 11 diagrams from `docs/diagrams/*.mmd` (three new for the guide: 09 two journeys, 10 trace one decision, 11 accuracy across runs, plus 12, a grid variant of the question set, because the wide README version was unreadable at page width) and 2 UI screenshots.
Alternatives: (B) Reuse README.md as the document. (C) A Claude Doc / web page.
Why A: The README is a reference for developers; the guide is for a reader who needs the why (reviewers, project staff). A Word file matches the stated preference and can be shared offline.
Verification: validated with the docx skill validator (all checks passed), rendered to PDF with LibreOffice and inspected page by page. Fixed: "Contents" listing itself in the TOC; unreadable figure 4 (replaced with the grid); headings left alone at page bottoms and a split code block (keep-with-next); an almost-empty page caused by an oversized routing figure. One factual error was caught against the code: the draft said the rules were "about 600 lines", but `triage/policy.py` is 270.
Trade-offs: The TOC page numbers fill in when Word updates fields (noted on the page). The figures are PNGs, so editing one means re-running `tools/render_diagrams.py` and then `tools/build_guide.js`.
