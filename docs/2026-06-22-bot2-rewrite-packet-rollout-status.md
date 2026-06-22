# Bot2 rewrite packet rollout status (2026-06-22)

## Summary
This document records the current landed state of the Bot2 rewrite-packet rollout in the mobile app and backend.

The main outcome of this round is that Bot2 rewrite is no longer a thin "suggestions string" path.
It is now a packet-driven rewrite flow with visible strategy preview, persisted debug state, and backend prompt contracts that differ by mode.

## Scope of this rollout

### Frontend state and persistence
Files:
- `static/mobile-app/src/stores/project.js`
- `app/models.py`

Landed state:
- project state now persists:
  - `self_review_text`
  - `reuse_system_suggestions`
  - `last_rewrite_packet`
- mobile store mirrors them as:
  - `selfReviewText`
  - `reuseSystemSuggestions`
  - `lastRewritePacket`
- these values are cleared on new project creation, restored on project load, and saved with the project payload

### Review page UX
File:
- `static/mobile-app/src/views/Review.vue`

Landed state:
- Review page now includes:
  - `我自己审`
  - custom self-review textarea
  - `复用系统建议` switch
- Review page computes a live `pendingRewritePacket` from current UI state
- Review page shows a visible `本轮改写策略` card before rewrite execution

Current strategy card surfaces:
- mode
- target type
  - `局部修补`
  - `整章重写`
- freedom policy
- instruction priority
- whether user self-review is enabled
- whether system brief participates
- a short mode hint describing the execution contract

### Rewrite packet generation
File:
- `static/mobile-app/src/lib/workflow.js`

Landed helpers:
- `getBot2FreedomPolicy(...)`
- `buildBot2RewritePacket(...)`
- `describeBot2RewritePacket(...)`

Current packet behavior:
- no self-review -> `system`
- self-review + reuse system suggestions -> `hybrid`
- self-review + do not reuse system suggestions -> `custom`
- full rewrite without self-review -> `full_rewrite`
- full rewrite with self-review + reuse system suggestions -> `full_rewrite_hybrid`
- full rewrite + do not reuse system suggestions still falls through to `custom`

Current freedom rules:
- default rewrite attempt progression:
  - first rewrite lane -> `high`
  - next -> `medium`
  - later -> `low`
- `custom` -> `bypass`
- `full_rewrite` / `full_rewrite_hybrid` currently force `high`

### Writing/rewrite dispatch
File:
- `static/mobile-app/src/views/Writing.vue`

Landed state:
- rewrite requests now build and send `rewrite_packet`
- successful rewrite persists:
  - `lastRewriteSuggestions`
  - `lastRewritePacket`
- ordinary write clears rewrite-only state

Important correction in this round:
- `全部重写` is no longer a legacy empty-array bypass
- it now emits a structured review-like payload with `force_full_rewrite: true`
- therefore full rewrite participates in the same strategy-generation / packet / prompt flow as suggested rewrite

### Backend prompt split
File:
- `app/routes/bot2.py`

Landed state:
- `_build_bot2_system(...)` now reads rewrite packet data in rewrite mode
- `_build_rewrite_user_prompt(...)` now builds mode-aware user prompts

Current backend-supported rewrite modes:
- `system`
- `hybrid`
- `custom`
- `full_rewrite`
- `full_rewrite_hybrid`

System-prompt layer now expresses:
- rewrite mode
- freedom policy
- instruction priority
- user self-review instruction
- system review brief

User-prompt layer now truly differs by mode:

#### `system`
- narrow targeted revision
- revise flagged passages only
- keep healthy passages stable
- do not rewrite the whole chapter

#### `hybrid`
- user-led rewrite
- system review only as compressed supporting brief
- user instructions outrank system review
- local restructuring allowed according to freedom policy

#### `custom`
- fully user-directed rewrite
- do not import omitted system-review items back into the task
- preserve continuity and chapter intent unless user explicitly wants change

#### `full_rewrite`
- full chapter rewrite driven by system brief
- do not preserve old draft sentence-by-sentence
- rebuild chapter around current chapter objective

#### `full_rewrite_hybrid`
- user-led full chapter rewrite
- system brief only gives direction
- do not preserve old draft sentence-by-sentence
- rebuild chapter around user goal + chapter objective

## Review/debug visibility
Files:
- `static/mobile-app/src/stores/project.js`
- `static/mobile-app/src/views/Review.vue`

Landed state:
- the actual latest rewrite packet is persisted in project state
- Review persistence now stores `rewrite_packet` inside saved review records

This makes it possible to explain later:
- why a rewrite was conservative vs aggressive
- whether a round was patch vs rebuild
- whether user instructions outranked system review
- whether the rewrite used supporting brief only or no system brief at all

## Validation run in this session

### Python syntax
```bash
python3 -m py_compile app/models.py app/routes/bot2.py
```

### Frontend build
```bash
cd /opt/NovelForge/static/mobile-app
npm run build
```

Both passed in the current environment.

## Current product meaning
Bot2 rewrite is now best understood as a local programmatic dispatcher rather than a single raw rewrite call.

The current closure already includes:
- packet generation
- strategy preview
- patch-vs-rebuild distinction
- persisted debugability
- backend system/user prompt alignment

## Still not addressed
This rollout does **not** yet solve:
- accumulated tips growth / pruning strategy
- resend cost of full draft text on rewrite
- stronger structured analytics for rewrite history beyond the latest packet snapshot
- a separate model-side `Bot2_1` dispatcher lane

## Practical conclusion
As of this rollout, the user can now see before clicking rewrite:
- what Bot2 mode will run
- whether this round is patch or rebuild
- how much freedom Bot2 will have
- whether user intent or system review is dominant

That is the main closure achieved in this round.
