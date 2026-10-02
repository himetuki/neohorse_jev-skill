# Validation snapshots

This separates package checks, live model calls, and agent-outcome evidence.
None substitutes for the others.

## This fork — NeoHorse-Jev-4B route (October 2026)

Fork-specific checks run against the modified package before publication:

- **114 unit tests pass** (`python -m unittest discover -s tests` over the whole
  suite), including the new `NeoHorseTests` class: endpoint mapping, key
  isolation, the https/host-allowlist guard (rejecting non-https, foreign hosts,
  lookalike domains and any address resolving into
  loopback/private/link-local/reserved ranges), presence-only setup reporting,
  and the documented reduced answer shapes.
- **Offline dry runs from the installed copies**: the general `jev` checkpoint
  asset plus all nine scenario `example.json` assets pass with both the default
  and `--provider neohorse`; every request maps the bundled model ID to
  `NeoHorse-Jev-4B`. No network call and no key are needed for these checks.
- **One real NeoHorse-Jev-4B call on a synthetic example** (ZCode + PowerShell,
  user-approved): a two-question triage request returned `queue: bug`
  (probability 0.947, margin 0.898) and `urgency: 1.11`, mode `jev_api`,
  transport `neohorse`, ~0.49 s round trip. The response confirmed the platform's
  documented shapes: choice answers carry `probabilities` without `confidence`,
  and score answers carry the full legend/probabilities envelope. The receipt was
  preserved by the caller. This verifies transport, auth and parsing; it is not a
  quality benchmark.
- **Credential hygiene**: no key literal exists anywhere in the repository; keys
  are read from the environment only, `setup` reports presence without values, and
  error messages never include provider response bodies.

Upstream snapshots below are historical records of the upstream project and were
## Upstream snapshots removed

The upstream project's dated validation snapshots — release checks, live-call
examples, the DeepSeek paired pilot and the BBH calibration campaign, together
with their receipts under `evals/results/`, `docs/updates/` and `docs/media/` —
were measured runs this fork did not perform, and have been removed rather than
presented as ours. Consult the upstream repository or this repository's git
history for them.

Verification for this fork = the section above: the offline suite, the installed
copy dry runs, the one user-approved synthetic NeoHorse call, and credential
hygiene checks.
