# Decision quality, calibration and escalation

A separate experiment from the [agent checkpoint pilot](README.md): **can Jev
choose the right label, and does uncertainty identify when not to rely on it?**
This evaluates decisions on public questions, not real autonomous execution or
Jev's training algorithm.

This fork keeps the frozen protocol but **removes the upstream measured
results**: no accuracy or calibration numbers are recorded here. Prepare and run
the campaign yourself before citing any threshold.

## Frozen protocol

- 160 English **BIG-Bench Hard** questions: 40 each from `disambiguation_qa`,
  `causal_judgement`, `logical_deduction_three_objects`, and `snarks`.
- Original input, option text, label direction and reference answer retained.
  No generated answers, translations, rewrites, or added fallback labels. In
  disambiguation, `Ambiguous` is a substantive answer, not a confidence abstention.
- Author repository revision `9ee07bd481feebf959a6b59d61ea57bdcf30964d`;
  `random.Random("20260920:<task>").sample(...)`, 40 unique indices per task.
  Sampling does not inspect labels. Save source hashes, original canaries,
  sample indices, exact samples, prompts, code snapshots and model settings.
- One Jev `typesafe/jev-1.13` call and one DeepSeek
  `deepseek/deepseek-v4.1-flash` call per item: **320 billed calls maximum**.
  Order alternates by item. Models never receive gold answers. No retries,
  model substitutions, few-shot demonstrations, or test-set threshold tuning.
- DeepSeek returns only a choice, with reasoning `none`, JSON mode and a
  512-token output ceiling. Its role is an accuracy comparator and potential
  reviewer, not an oracle. We do not fabricate a probability distribution from
  its selected label or claim equal-compute comparison.
- Jev returns its native Choice distribution and separate `confidence` field.
  No deployed CLI thresholds or permissions are changed by this experiment.

[Dataset origins and licenses](THIRD_PARTY.md) ·
[HF and Chinese/English follow-up dataset menu](../skills/jev/references/decision-datasets.md)

## Run and reproduce

```sh
# Downloads four small public author JSON files; no model API calls.
python -m evals.calibration --output evals/results/calibration-your-run
# Inspect manifest.json and samples.json before opting into charges.
export OPENROUTER_API_KEY='...'
python -m evals.calibration --live --output evals/results/calibration-your-run
```

The second command requires the frozen samples and code to remain unchanged.
It exclusively creates `events.jsonl`: an existing receipt file cannot be
reused or overwritten. All responses, errors, returned model IDs, usage and
wall times are retained, without authorization headers. Fatal HTTP
400/401/402/403/404 stops the campaign and writes `aborted.json`; partial or
aborted campaigns are not reported as completed results.

The per-item output is classification only. No browser, financial operation,
human reviewer, or other external action is invoked.

## Measures and denominators

- **Accuracy:** exact match / all 160 attempts, including API/schema errors as
  wrong. Also disclose valid-response accuracy and coverage per task.
- **Brier:** mean sum across classes of `(p - one_hot(gold))²` (not divided by
  class count). This measures probabilistic quality, not calibration alone.
- **NLL:** natural-log loss; clamp gold probability at `1e-12` and disclose
  exact-zero gold probabilities. The API's rounded zeros are not proof that
  its internal probability is literally zero.
- **Reliability / ECE:** top-label probabilities in 10 equal-width bins
  `[0,.1), …, [.9,1]`, with counts, mean probability and observed accuracy.
  ECE is the count-weighted absolute gap. Brier/NLL/ECE use valid responses;
  they cannot conceal failures excluded from those probability metrics.
- Jev rounds distributions. Accept only the CLI's small sum tolerance, then
  normalize for scoring and top-probability routing; preserve raw values and
  count normalized vectors. Never normalize arbitrary invalid weights.
- Preserve `confidence` separately. A similarly computed score/accuracy gap
  is a **shape-statistic diagnostic**, not a claim that this field forecasts
  correctness. Do not confuse it with probability ECE.

See [calibration semantics and sources](../skills/jev/references/calibration.md).

## The proposed three-way policy

We predeclare two **offline** routing simulations, one consuming normalized
maximum option probability and the other consuming raw API `confidence`:

| Score | Candidate consumer |
|---|---|
| `>= 0.90` | Jev's label |
| `>= 0.70` and `< 0.90` | DeepSeek's independently collected label |
| `< 0.70` or invalid Jev result | Human queue, left unresolved |

Equality belongs to the upper band, removing boundary gaps. Each score's bands
include count, coverage, Jev's initial-label accuracy, selective risk
(`1 - that accuracy`) and Wilson 95% intervals. These are **Jev diagnostics**,
not accuracy or uncertainty intervals for DeepSeek or human decisions. These intervals are descriptive: correlated/public items and
multiple comparisons weaken population interpretations. Small buckets and ECE
bins are especially uncertain.

The protocol collects both models on **all** items to inspect the comparator; replaying
only the selected labels estimates a cascade's classification behavior, reported
separately from those Jev-band diagnostics. It does
not measure real cascade cost/latency savings or human accuracy. Human-routed
items receive **no oracle success credit**. Required permissions, explicit
fallback labels, verification, and high-impact approval remain separate host
gates. A high-confidence `Ambiguous` answer does not authorize an action.

## What this can and cannot establish

This small zero-shot reasoning/interpretation stress test can reveal mistakes,
overconfidence and review-load tradeoffs. It is not an industry workflow test,
a full BBH score, an unseen-data guarantee, a language comparison, or a universal
validation of 0.9/0.7. Public tasks may occur in model training. Causal judgment
and sarcasm depend on human conventions; benchmark agreement is not metaphysical
truth. Logical deduction intentionally probes a documented weak area.

Do not retrofit thresholds to these results and call them validated. A deployment
needs independently labeled, task-matched development and held-out sets, costs
for different errors, and monitoring after model/domain changes. Chinese
Ruozhiba questions are promising qualitative stress cases, but GPT-generated
solutions are **not** independent ground truth; label them separately first.

## Post-hoc label-format diagnostic

During the first run, some DeepSeek JSON responses used `"A"` where the native
option key was `"(A)"`. The frozen strict parser rejects that spelling. Original
receipts and strict results remain unchanged; this is an interface failure,
not necessarily an incorrect semantic judgment.

A **secondary, post-hoc** audit accepts only this exact mechanical repair:
`{"choice":"X"}` → `{"choice":"(X)"}` when X is one uppercase letter and
`(X)` is an original option. It never consults the gold answer to decide whether
to repair, never accepts extra JSON keys, and never rescues transport failures.
Other failures remain wrong. It reports recovered IDs, normalized base accuracy,
and a separately labeled cascade replay, without any new model calls:

```sh
python -m evals.calibration_label_audit evals/results/calibration-your-run
```

`label-audit.json` is a separate artifact. This normalization was **not
preregistered**; report strict and normalized results together. Future comparisons
should predeclare a shared label-normalization rule or use an equally constrained
label schema, rather than changing a test prompt after seeing answers.
