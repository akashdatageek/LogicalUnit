# Corpus plan — from 10 to 100 without cherry-picking

## Sampling frame
Define it once and cite it: GitHub repos via a fixed query (SEART GHS export or the
GitHub search API with fixed filters, snapshot date recorded). Inclusion: primary
language in {Python, TypeScript, Go, Rust, Java, C++}; 1k–150k source LOC; ≥ 50 commits;
not a fork; not archived (exception: UAV stratum); permissive licence; builds or at least
resolves imports without network.

## Strata (random sample WITHIN each; record the seed of the sampler)
| Stratum | Purpose | n |
|---|---|---|
| famous (>5k stars) | comparability with prior work; contamination-prone | 30 |
| low-visibility (<200 stars, >1 yr old) | contamination-resistant | 30 |
| post-cutoff (created after the model's training cutoff) | contamination-proof | 15 |
| natural-partition (workspace / plugins / packages layout) | ceiling / recall control | 10 |
| UAV / robotics | thesis evaluation domain | 15 |
Cross-cut each stratum by language and size bucket (1k / 10k / 50k / 150k LOC) as evenly
as the frame allows. Report results per stratum. Pooled numbers only in the appendix.

## Dev / holdout
70 dev / 30 holdout, split by stratified random draw BEFORE any skill edit. Holdout is
scored once, by the human, at the end. Current 10: 7 dev / 3 holdout (harness/holdout.txt).

## Gold subset
Pick 10 repos (2 per stratum). Two annotators produce an LU manifest independently from
the skill's definition; report inter-annotator ARI; reconcile into gold/<repo>.json.
This is the only ground truth. Everything else is a proxy and must be labelled as such.
For comparison with the architecture-recovery literature use MoJoFM against these golds.

## Second model
Reserve the final 10 dev repos' worth of budget for RQ5: baseline skill vs final skill
on a second model. Without this you cannot claim the skill generalises beyond one model.
