# Install Jev Skills with your agent (NeoHorse-Jev-4B fork)

> **Fork notice.** This repository is a fork of
> [wuyoscar/jev-skill](https://github.com/wuyoscar/jev-skill) v0.2.0. The default
> real route is repointed at the **NeoHorse-Jev-4B** decision endpoint on
> tokenrhythm.studio (`--provider neohorse`, key `NEO_HORSE_API_KEY` read from the
> local environment only). The OpenRouter and official TypeSafe routes remain
> available and are never switched silently. Everything else — the skills,
> scenarios, simulation mode and safety rules — follows the upstream design.

## For people

Copy this into **ZCode, Codex, Claude Code or OpenCode**:

```text
Install Jev Skills for my current agent, including the general skill and all scenario skills. Read and follow this installation guide, then verify the installation:
https://raw.githubusercontent.com/himetuki/neohorse_jev-skill/main/docs/install.md
```

中文：

```text
帮我给当前 Agent 安装 Jev Skills，包括通用技能和全部场景技能。请读取并按照这份安装指南操作，完成后验证安装是否成功：
https://raw.githubusercontent.com/himetuki/neohorse_jev-skill/main/docs/install.md
```

You do not need to run terminal commands yourself. The agent needs file access
and permission to run installation commands. It may need your help with a missing
runtime or a permission prompt. If there is no key, it must first ask you to
choose **A: get a key** or **B: simulate with your current agent or another
explicitly approved available model**. Never paste a key into chat.

## For the installing agent

### Outcome and defaults

Install all eleven skill folders from the fork for the current host. This fork
practices the NeoHorse-Jev-4B route in ZCode, so the default real-service route is
`--provider neohorse` against `https://tokenrhythm.studio/v1/decision` with
`NEO_HORSE_API_KEY`; OpenRouter and TypeSafe stay available as explicit choices.
Install the runtime for Jev API mode; it is not needed for agent simulation.
Verify the copied files and run applicable offline checks. Default to
**project-local** installation in the current project, or the host's user-level
skill directory when the host documents one (ZCode: `~/.zcode/skills`). Say which
host and destination you selected before writing. If the host/project cannot be
determined, ask one short question rather than installing into every detected
client or a random working directory. Honor an explicitly requested subset or
installation scope.

This is an installation task, not permission to change the agent's main model,
MCP servers, hooks, security settings or unrelated skills. Do not install any
linked community project. No Vercel account, gateway or Node/npm is needed for
the direct-copy route below. Existing host approval requirements still apply.

### 1. Check the environment

- Identify the current host from the session, not merely from installed binaries.
- Locate the actual project root and read any applicable local instructions.
- Follow the included `jev-setup` route selection. Check only presence of
  `NEO_HORSE_API_KEY`, `OPENROUTER_API_KEY` and `TYPESAFE_API_KEY`; never values.
  Respect a route the user already configured. For a new setup on this fork,
  offer the NeoHorse-Jev-4B platform first (https://tokenrhythm.studio), then
  OpenRouter or official TypeSafe. Explain and obtain a choice before changing
  providers or sending data.
- If no route is configured, warn and ask, then **wait**:
  **A:** configure a real Jev key (NeoHorse-Jev-4B platform key, OpenRouter, or
  TypeSafe); **B:** simulate with the current agent or a specifically approved
  available model such as DeepSeek. B outputs say `jev_called: false`, identify
  `agent_simulation` or `model_simulation`, and keep probability/confidence null.
  Never silently simulate or install another model. Keys stay outside chat.
  A can finish offline installation before key setup; installation is not
  permission to make paid calls. B needs no Jev key or Jev Python CLI.
- Check for Git; if unavailable, download the release source archive with an
  available tool instead. **For API mode**, also check for Python **3.10+** and
  an existing `uv` or `pipx`. Explain missing prerequisites and obtain any required
  approval to install them. Do not use `sudo`, modify system Python or silently
  switch products. **B needs none of these Python/CLI dependencies**; do not
  require or install them just for agent simulation.
- Inspect existing `jev-decide` and destination skill folders. Leave identical
  installations alone. For different versions, local edits or symlinks, explain
  the conflict and get confirmation before replacing them; never merge blindly.

### 2. Download and inspect the pinned source

Use a fresh temporary directory. For example, in a POSIX shell:

```bash
work=$(mktemp -d)
git clone --depth 1 --branch neohorse-jev-4b https://github.com/himetuki/neohorse_jev-skill.git "$work/source"
git -C "$work/source" rev-parse HEAD
```

Record the resolved commit in your installation report; do not substitute `main`
or an unverified branch for the reviewed source. Inspect `pyproject.toml`, the
skill entrypoints and `skills/jev/scripts/jev.py` before running downloaded code.
On Windows, use equivalent temporary-directory and file operations in the host's shell.

### 3. Install the shared CLI

**Skip this step for B.** Use the selected existing agent/model interface.
For API mode:

Use **one existing** package tool, not both:

```bash
uv tool install "$work/source"
# Alternative when pipx is the available tool:
# pipx install "$work/source"
```

Do not use `--force` to replace an existing command without resolving the conflict.
Check that `jev-decide --help` works in the environment the host uses. If the
installation directory is not on PATH, locate it using the package tool and verify
the executable by its absolute path. Report the PATH/restart step still needed;
do not silently edit shell startup files. A new terminal or restarted host may be
needed to inherit PATH changes **and** to pick up a newly set environment
variable such as `NEO_HORSE_API_KEY`.

For a user who explicitly wants **only `jev`**, skip CLI installation: that skill
bundles `scripts/jev.py` and runs with Python alone. Do not silently substitute
this smaller installation for the full collection requested above.

### 4. Copy the complete skill folders

Choose only the current host's destination:

| Current host | Destination |
|---|---|
| ZCode | `~/.zcode/skills/` (user-wide) or `<project>/.zcode/skills/` |
| Codex | `.agents/skills/` |
| Claude Code | `.claude/skills/` |
| OpenCode | `.opencode/skills/` |

Copy each whole folder from `<source>/skills/`, including its assets and any
scripts/references, preserving the folder name:

- `jev`
- `jev-triage`
- `jev-documents`
- `jev-ui`
- `jev-route`
- `jev-context`
- `jev-code-review`
- `jev-find-code`
- `jev-simulation`
- `jev-setup`
- `jev-redteam`

Preflight **all** destinations for conflicts before writing any folder. Use the
host's filesystem tools or `shutil.copytree` without overwrite/merge options.
Keep the download outside the target skills directory, and do not copy `.git`,
the entire repository or just the eleven `SKILL.md` files. In API mode the focused
skills need the shared CLI; the general skill includes its own script.

For explicitly requested user-wide installation, resolve the current host's
supported user skill directory from its documentation first. Do not infer a
user-level path by prepending `~` to the project-local table.

### 5. Verify from the installed copies, without a key or API call

In **both modes**, confirm every copied `SKILL.md` and its linked local
assets/references exist. Check that each installed skill includes the A/B consent
instructions and explicit simulation labels.

In **API mode**, run the following checks. In B, they are optional if the runtimes
already exist; otherwise report them as skipped, not passed. Do not install
dependencies solely to run CLI checks for B.

Resolve `<installed-jev>` to the copied general-skill directory:

```bash
python3 <installed-jev>/scripts/jev.py decide <installed-jev>/assets/checkpoint.json --dry-run
python3 <installed-jev>/scripts/jev.py decide <installed-jev>/assets/checkpoint.json --provider neohorse --dry-run
```

Then run the installed shared CLI on **each of the nine** copied scenario assets,
once per selected provider:

```bash
jev-decide decide <installed-scenario>/assets/example.json --dry-run
jev-decide decide <installed-scenario>/assets/example.json --provider neohorse --dry-run
```

The ninth scenario is `jev-redteam`. `jev-setup` has no classification asset: verify its
entrypoint and `references/simulation.md`, then run `jev-decide setup` if the CLI
is installed. Its report must not expose a key or make a network request.

These commands must exit 0 and print the validated request. Use absolute paths
if needed; a source-checkout test is not a copied-installation test. Ask the host to
refresh skill discovery if it supports that; otherwise explain whether a restart
or new session is needed. Do not claim native invocation was tested merely because
files were copied.

### 6. Explain what is ready

Report host/destination, installed skills, selected mode, key present/missing,
checks passed/skipped and CLI version/location if installed. Separate **installed**,
**verified offline**, **agent simulation selected** and **ready for API calls**.
A key-presence check does not prove that the key works; that requires a successful
API response. Copied skill files alone do not prove native agent behavior.

For A with a key still missing, explain local environment setup for the host —
for the fork's default route that is the user-level variable
`NEO_HORSE_API_KEY` (Windows: *Settings → "Edit environment variables for your
account" → New…*, or
`[Environment]::SetEnvironmentVariable('NEO_HORSE_API_KEY','…','User')`), then a
host restart so child processes inherit it. Do not collect it in chat, store it in
the repository or copy other apps' secrets.
For B, use the selected existing agent/model interface and mark all outputs as simulated, with
`probability` and `confidence` set to `null`. Do not send requests to Jev, require
a key, fabricate receipts or use probability thresholds to authorize actions.
Do not silently switch modes if a key later appears or an API call fails.

Do not spend API credits just to install. Once the user requests a real example,
use a small synthetic input and the selected skill; preserve the receipt.

A first-use prompt to offer:

> Use jev-triage to classify these messages into billing, bugs, how-to and other.
> Show the labels and uncertain cases before changing anything.

## Manual installation and troubleshooting

[CLI options, provider setup, manual paths and compatibility](installation.md).
The optional `npx skills` route there is just another way to copy skills; it is
not a Vercel runtime dependency. Upstream's dated run records were removed in
this fork because they were measurements this fork did not perform.

## Verify the selected provider without spending

Run `jev-decide setup` for a read-only presence report, then dry-run a prepared
example with the selected `--provider`. This fork's default route is NeoHorse:
`--provider neohorse` posts to `https://tokenrhythm.studio/v1/decision`, pins
model `NeoHorse-Jev-4B` and reads `NEO_HORSE_API_KEY`; the other routes are
OpenRouter (`https://openrouter.ai/api/alpha/decisions`, `OPENROUTER_API_KEY`,
model `typesafe/jev-1.13`) and official TypeSafe
(`https://api.typesafe.ai/v1/systemone`, `TYPESAFE_API_KEY`, model `jev-1.13.0`).
No route auto-falls back. The known bundled OpenRouter model ID maps to the
selected provider's model. A dry run does not authenticate the key or verify
credits, and the wrapper enforces https, a documented-host allowlist and rejects
addresses that resolve into loopback/private/reserved ranges.
For simulation, use `jev-setup/references/simulation.md` with the selected existing
model, not the Jev CLI. See `jev-redteam` for offline batch/session examples.
