# Topic model — full reference

Daily Scholar drives both **paper discovery** and **learning content** (reviews, quizzes) from a single first-class **Topic** entity. This doc covers the full schema, the YAML ↔ DB round trip, the in-app editor, scope (silo / multi / all), and a step-by-step for authoring a new stream.

> For a one-paragraph overview, see [Configuration in the README](../README.md#the-unified-topic-model).

---

## What a Topic is

One topic = one YAML file under `config/topics/<id>.yaml` + one row in the `topics` DB table. Each topic drives two surfaces:

- **Paper discovery** — `keywords`, `arxiv_categories`, `weight`, `min_relevance`, `recency_days` shape what arXiv / Semantic Scholar papers get surfaced and how strongly they match.
- **Review + quiz generation** — `key_concepts`, `learning_objectives`, `resources`, `quiz_difficulty` feed the LLM prompts that produce topic reviews and quiz questions.

Both surfaces read from the same row, so a topic edit (whether via YAML or the UI) immediately affects everything downstream.

---

## Schema

Every YAML carries the same fields. Most are optional with sensible defaults.

```yaml
# config/topics/ml-foundations.yaml
id: ml-foundations                   # stable slug, used in URLs and DB foreign keys
name: ML Foundations — Neural Networks, Training, Classification, Fine-tuning, Diffusion
stream: foundations                  # grouping label, used by the UI for the streams sidebar
active: true                         # quick on/off without deletion (default: true)
weight: 1.5                          # multiplier on relevance scoring (default: 1.0)

# ---- paper-discovery side -----------------------------------------------
keywords:                            # match against paper title + abstract
  - neural network
  - transformer
  - LoRA
  # ...
arxiv_categories:                    # arXiv taxonomy filter
  - cs.LG
  - cs.AI
  - stat.ML
recency_days: 180                    # exclude papers older than N days (default: 30)
min_relevance: 0.18                  # discard papers scoring below this (default: 0.18)

# ---- learning-content side ----------------------------------------------
key_concepts:                        # bullet-list, fed verbatim into review/quiz prompts
  - the structure of a feedforward neural network
  - "the basics of training: loss, gradient descent, backprop, optimizer choice"
  # ...
learning_objectives:                 # actionable, verifiable statements
  - Diagram a forward pass through a small MLP and explain what backprop computes
  - Compute macro F1 from a small confusion matrix by hand
  # ...
resources: []                        # optional reading list (URLs or citation strings)
quiz_difficulty: easy                # easy | medium | hard — informs question complexity
prerequisites: []                    # other topic ids that should be reviewed first
```

### Field reference

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | string | — | Required. Stable kebab-case slug. Used in URLs (`/topics/<id>/review`) and as the FK. Changing this is breaking. |
| `name` | string | — | Required. Human-readable display name. |
| `stream` | string | `null` | Grouping label for the streams sidebar in the UI. Topics with the same stream cluster together. |
| `active` | bool | `true` | If false, the topic is hidden from discovery, review, and quiz. Row stays. |
| `weight` | float | `1.0` | Multiplier on the relevance score during paper discovery. Higher = more papers from this topic. |
| `keywords` | list[string] | `[]` | Substring-matched against paper title + abstract (case-insensitive). |
| `arxiv_categories` | list[string] | `[]` | arXiv taxonomy codes (e.g., `astro-ph.HE`, `cs.LG`). Papers must match at least one. |
| `recency_days` | int | `30` | Discovery window in days. Per-topic so transient papers can have a different freshness ceiling than survey papers. |
| `min_relevance` | float | `0.18` | Papers scoring below this are discarded post-discovery. Tune up for stricter focus. |
| `key_concepts` | list[string] | `[]` | Fed verbatim into review + quiz LLM prompts. The "what should the user learn?" list. |
| `learning_objectives` | list[string] | `[]` | Actionable, verifiable statements. Quiz generator uses these to anchor questions. |
| `resources` | list[string] | `[]` | Optional reading list shown alongside reviews. Plain URLs or citation strings; not rendered specially. |
| `quiz_difficulty` | enum | `medium` | `easy` / `medium` / `hard`. Informs the LLM's question complexity. |
| `prerequisites` | list[string] | `[]` | Topic ids that should be reviewed first. Currently informational; future scope: enforce ordering. |

---

## How topics get into the database

`config/topics/*.yaml` is the **bootstrap source**. On every backend startup the loader scans this directory and inserts any topics that aren't yet in the DB. After the first bootstrap, **the DB is canonical** — YAML edits do NOT auto-overwrite UI-edited rows.

Three operations bridge YAML and DB:

| Operation | When to use | Endpoint | Effect |
|---|---|---|---|
| **Bootstrap** | every cold start | (automatic, in lifespan) | INSERT new YAML topics; mark missing YAML files as orphaned (`source_yaml_present = false`) |
| **Import YAML → DB** | you edited a YAML and want it to win | `POST /topics/import-yaml` | OVERWRITE every DB field with YAML values for topics present in YAML |
| **Export DB → YAML** | you edited a topic in the UI and want the YAML to reflect it | `POST /topics/export-yaml` | Write the current DB state out as one file per topic under `config/topics/` |

Both endpoints are also surfaced as buttons on `/topics` in the UI.

### Why this split

Cloud filesystems are ephemeral on Railway — `config/topics/*.yaml` from the deployed image is read-only and can't accept UI writes. So the DB is the runtime source of truth, and YAML is the long-lived, version-controlled artifact. The bootstrap loop preserves UI edits across restarts; the explicit import/export operations let YAML authors and UI editors override each other only when they mean to.

---

## Editing topics from the UI

Visit `http://localhost:3000/topics` (or the hosted equivalent) to manage topics in the browser:

- **Create**: `+ New topic` — written to DB only. Use **Export DB → YAML** afterwards to commit the new topic to the working tree.
- **Edit**: pick a topic, change any field, save. UI edits persist across re-bootstraps until you explicitly `POST /topics/import-yaml`.
- **Soft-delete**: toggle **Deactivate** (sets `active=false`). The row stays; discovery / review / quiz skip it. Reactivate any time.
- **Hard-delete**: **Delete** button (with confirm). Removes the row entirely. The YAML file on disk is unaffected — re-bootstrap will resurrect it unless you also delete the YAML.
- **Filter**: by stream, include or exclude orphaned topics (YAML missing on disk).

### Orphaned topics

A topic whose row exists in the DB but whose YAML file is no longer on disk is flagged `source_yaml_present = false`. The UI shows these with a small "no YAML" badge; they still work — discovery, review, and quiz all use them — but they won't survive a `POST /topics/import-yaml` unless you re-create the YAML first.

The most common source of orphans: deleting a YAML file from `config/topics/` without also calling `POST /topics/import-yaml` (which would mark them as deleted from DB). Easiest cleanup: re-export, then either restore the YAML or hard-delete the DB row.

---

## Switching focus: silo / multi / all

**Scope** controls which topics actually drive paper discovery, reviews, and quizzes. Independent of which topics are `active` (which is a permanent flag), scope is a per-session selector you tune to your current focus. Set it from `/settings/scope`:

| Mode | What it does | When to use |
|---|---|---|
| **All active** | Every `active=true` topic contributes. The default. | Default. Broadest coverage. |
| **Multi-select** | Only the topics you pick from a checklist. | "This week I want to work in streams A and B." |
| **Silo** | Exactly one topic — discovery and content generation go deep on it alone. | Cramming for a specific deliverable; deep-diving a new area. |

Scope persists per-user on the server (`user_settings.scope_mode` + `scope_topic_ids`). Changes take effect on the next discover / review / quiz call.

---

## Step-by-step: authoring a new stream

Walkthrough for adding a new topic from scratch. Example: a topic on "Approximate Bayesian Computation."

### 1. Decide the slug and stream

`id` is the stable kebab-case slug used in URLs and DB joins. `stream` groups topics in the UI. Pick both before you start typing:

```
id:     approximate-bayesian-computation
stream: bayesian-methods
```

### 2. Create the YAML file

```bash
nvim config/topics/approximate-bayesian-computation.yaml
```

```yaml
id: approximate-bayesian-computation
name: Approximate Bayesian Computation (ABC) for Implicit Models
stream: bayesian-methods
active: true
weight: 1.0

keywords:
  - approximate Bayesian computation
  - ABC
  - likelihood-free inference
  - simulation-based inference
  - SBI
  - sequential Monte Carlo
  - SMC-ABC
  - neural posterior estimation
  - NPE
  - summary statistic
arxiv_categories:
  - stat.CO
  - stat.ME
  - stat.ML
recency_days: 365                    # ABC literature is slower-moving; widen the window
min_relevance: 0.20                  # tighter — keep noise out

key_concepts:
  - why a likelihood-free posterior is needed when the simulator has no tractable likelihood
  - the rejection-ABC algorithm and its sample-efficiency problem
  - sequential Monte Carlo for ABC (SMC-ABC) and what each step buys you
  - choosing summary statistics and the curse of dimensionality
  - neural posterior estimation as a modern alternative to classical ABC

learning_objectives:
  - Identify when ABC is appropriate vs. when a likelihood-based method is preferable
  - Walk through one SMC-ABC iteration on a toy 1D problem
  - Explain how poorly chosen summary statistics bias the posterior

resources:
  - https://arxiv.org/abs/1101.0955     # Sisson, Fan, Beaumont — Handbook of ABC, intro chapter
  - https://www.mackelab.org/sbi/      # sbi toolkit docs

quiz_difficulty: medium
prerequisites:
  - ml-foundations
```

### 3. Bootstrap it into the DB

```bash
make start
# (or just restart the backend if it's already running)
```

The lifespan hook scans `config/topics/`, sees the new YAML, and inserts the row. You'll see a log line like:

```
↳ Topics bootstrapped: 1 inserted, 7 preserved, 0 marked orphaned
```

### 4. Verify it shows up

```bash
curl -s http://localhost:8000/topics | jq '.[] | select(.id == "approximate-bayesian-computation")'
```

…or visit `http://localhost:3000/topics`.

### 5. Iterate

Tweak `keywords` until paper discovery surfaces the right papers; tighten `min_relevance` if too much noise sneaks through. Two ways to iterate:

- **Edit the YAML** + `POST /topics/import-yaml` (or just restart). Best for systematic, reviewable changes you want in git.
- **Edit in the UI** at `/topics/approximate-bayesian-computation/edit`. Best for rapid trial-and-error. When you're happy, `POST /topics/export-yaml` to write the changes back to the YAML.

### 6. Commit

Once the topic is dialed in:

```bash
make start --backend-only            # ensure DB matches YAML
# or, if you've been editing in the UI:
curl -X POST http://localhost:8000/topics/export-yaml

git add config/topics/approximate-bayesian-computation.yaml
git commit -m "topics: add Approximate Bayesian Computation stream"
```

---

## Archived / pre-unified configs

The legacy `config/interests.yaml` and `config/courses.yaml` (from before the unified Topic model landed in Phase 0) are preserved at `config/_archive/*.bak` for reference but never loaded. A flattened Topic version of the broad-ML focus lives at `config/topics/_archive/generic-ml.yaml` — restore it any time:

1. `mv config/topics/_archive/generic-ml.yaml config/topics/generic-ml.yaml`
2. Restart the backend (or `POST /topics/import-yaml`)
3. Optionally `active: true` in the YAML to turn it on immediately

---

## Common gotchas

| Symptom | Cause | Fix |
|---|---|---|
| "Topic exists in DB but YAML edits don't apply" | Bootstrap only INSERTs new topics; existing rows are preserved | `POST /topics/import-yaml` to overwrite |
| "Created a topic in the UI but it disappears on restart" | DB has it, but no YAML → bootstrap doesn't re-add it. (Restart doesn't remove it either — UI rows survive cold starts) | If you want it in git, `POST /topics/export-yaml` to write the YAML |
| "Discovery returns nothing for my new topic" | Most likely `min_relevance` too high, `keywords` too narrow, or `arxiv_categories` excludes the field | Loosen `min_relevance` to 0.10 temporarily; check `/papers/discover` output |
| "Quiz questions feel generic" | LLM has nothing to anchor to — `key_concepts` / `learning_objectives` are sparse | Add 5-10 concrete `learning_objectives` written as actionable statements |
| "Orphaned" badge on a topic I just edited | YAML file is missing from `config/topics/` even though the DB row exists | Either restore the YAML or hard-delete the DB row |
