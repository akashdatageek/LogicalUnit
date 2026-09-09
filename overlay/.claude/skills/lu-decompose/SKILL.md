---
name: lu-decompose
description: Decompose this repository into Logical Units and write /out/manifest.json. Invoke with /lu-decompose. Read-only on source.
disable-model-invocation: true
---

# Decompose this repository into Logical Units

You are producing a **manifest**, not a refactor. You never edit source. The only
file you write is `/out/manifest.json`. The run is not finished until that file
exists and `ent ci --lint /out/manifest.json` reports zero blocking errors, OR the
manifest lists every unpartitioned file with a reason.

## What a Logical Unit is

A Logical Unit (LU) is:

1. a **name** and a one-paragraph **plain-language description** a non-programmer
   can follow (what it is for, what it does, what it must never do);
2. an **exclusively-owned set of source files** — every file belongs to exactly one
   unit;
3. a **contract**:
   - `entrypoints`: the enumerated, typed ways other code or the outside world
     enters this unit (exported functions/classes, CLI commands, HTTP routes,
     message handlers). If it isn't listed, it isn't an entrypoint.
   - `depends_on`: which *entrypoints of other units* this unit calls. Edges
     target entrypoints, never files or units-as-a-whole.
   - `effects`: declared external effects — network, filesystem, database,
     subprocess, environment, clock, randomness. Undeclared effects are violations.

Units are one of two kinds:
- **domain** — encodes what the project is *about* (routing rules, parsing,
  vehicle commands, query planning).
- **infra** — encodes how the project talks to the world or to itself (HTTP
  client, config loading, logging, DB session, MAVLink transport). Domain units
  depend on infra units through their contracts; infra units are mockable from
  their contract alone.

## The five invariants (checked mechanically, not by you)

| # | Invariant | What `ent ci` checks |
|---|-----------|----------------------|
| 1 | Partition | every source file in exactly one unit |
| 2 | Enumerated entrypoints | each listed entrypoint resolves to a real symbol/route; exported symbols not listed are flagged |
| 3 | Edges target entrypoints | every `depends_on` edge resolves to a listed entrypoint of the named unit |
| 4 | Effects declared | detected I/O calls in a unit's files are covered by its `effects` |
| 5 | Version | hash(own content ⊕ dependency contract hashes) — computed by `ent`, you never write it |

Your job is to make 1–4 true. `ent` computes 5.

## Procedure

Work in this order. Do not skip the survey.

### Step 1 — Survey (lead, ~10% of budget)
- List the tree. Identify source vs. tests vs. generated vs. vendored vs. docs.
  Tests, docs, CI, and vendored code are **out of scope**: list them under
  `excluded` with a reason. Generated code is in scope if it is imported.
- Find the entry surface: `__init__`/`index`/`mod.rs`/`main`, CLI declarations,
  route registrations, public exports, `pub` items, `package.json` `exports`.
- Find the seams: places where one part of the code calls another only through
  a narrow interface. Seams become unit boundaries. Directories are a *hint*,
  not a boundary — see anti-patterns.
- Write a candidate list of 3–15 units with a one-line rationale each.

### Step 2 — Scout (parallel, one `unit-scout` subagent per candidate)
Give each scout: the candidate name, its rationale, and the file list you
think it owns. The scout returns a JSON contract proposal (see schema). Scouts
are read-only and cannot see each other's output.

### Step 3 — Reconcile (lead)
- Merge scout proposals. Resolve file ownership conflicts: a file goes to the
  unit whose entrypoints it most directly serves.
- Rewrite every `depends_on` edge so it targets a listed entrypoint. If unit A
  calls something in unit B that B did not list as an entrypoint, either B's
  entrypoint list is incomplete (add it) or A is reaching into B's internals
  (note it under `violations_observed`; this is a finding, not a failure).
- Check kind assignments: a unit with effects but no domain logic is infra.
  A unit with no effects and no entrypoints is probably not a unit — merge it.

### Step 4 — Write and lint
- Write `/out/manifest.json` conforming to `lu-manifest.schema.json`.
- The lint hook runs automatically on write and returns violations. Fix and
  rewrite. Budget: at most 5 lint rounds. If violations remain after 5,
  leave them in and add each to `unpartitioned` or `violations_observed`
  with an honest reason.

### Step 5 — Stop
You may stop only when `/out/manifest.json` exists. The stop hook enforces this.
Do not ask the user anything; there is no user. Do not summarise in prose; the
manifest is the deliverable.

## Anti-patterns (each of these is a known way to score badly)

- **One giant unit.** Passes the partition invariant trivially. Scores below the
  null baseline. If you have fewer than 3 units for a repo over 2k LOC, you have
  not found the seams.
- **One unit per file / per directory.** Also trivial; also scored against a
  baseline. Directories are how the *author* organised files, which is often but
  not always how the *logic* is organised. Use them as a starting hypothesis
  and break them when a seam crosses a directory.
- **Listing every symbol as an entrypoint.** Entrypoints are what *other units
  or the world* enter through. Internal helpers are not entrypoints, even if
  exported for testing.
- **Depending on a unit rather than an entrypoint.** `depends_on: ["http-client"]`
  is invalid. `depends_on: [{"unit":"http-client","entrypoint":"Session.request"}]`
  is valid.
- **Describing the code instead of the logic.** The `description` field is for
  a layperson: "Turns a URL and options into a request the server understands,
  and turns the server's reply into an object the caller can inspect" — not
  "Contains PreparedRequest and Response classes."
- **Silently dropping files.** Every source file is either in a unit, in
  `excluded` with a reason, or in `unpartitioned` with a reason.

## Worked example

See `examples/minimal-http-lib.manifest.json` — a 6-file toy library split into
one domain unit and two infra units. Copy its *shape*, not its content.

## Budget

If you are past 60% of your turn budget and have no manifest yet, write the best
partial manifest you can and continue refining it in place. A partial manifest
with an honest `unpartitioned` list beats no manifest.
