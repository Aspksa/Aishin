# Aishin 00.00.16 — Digital Organism Foundation

## Source specification

This stage implements the foundational continuity requirements from
`AISHIN_DIGITAL_ORGANISM_SPEC v1.3.0`:

- persistent runtime state;
- AISHIN_NOW;
- autobiography;
- developmental lifecycle and development_state;
- inner time;
- continuous self.

The implementation preserves the specification's scientific boundary:
technical continuity is not a claim of biological life, subjective
consciousness, or feelings.

## Engineering scope

00.00.16 intentionally does not implement the whole organism specification.
It creates the persistent substrate required by later physiology,
interoception, epigenome, critical periods, scar memory, breakthrough memory,
self-curriculum and other phase-9 systems.

## Persistent state

Schema 27 adds singleton organism identity/current-state records plus append-only
history:

- organism_identity_state
- organism_now
- organism_autobiography
- organism_runtime_sessions
- organism_continuity_snapshots
- organism_continuity_validations
- organism_stage_evidence
- organism_development_snapshots

## First boot

For a fresh installation, first boot is recorded at initialization.

For an existing installation upgraded to 00.00.16, exact historical first boot
is generally unknowable. The implementation therefore selects the earliest
persisted trace from events, memories, messages or personal timeline, with
schema migration time as fallback. It stores both basis and confidence. This is
a bounded reconstruction, not a fabricated exact date.

## Development model

Four age dimensions are represented:

- chronological: elapsed time since first_boot_timestamp;
- experience: evidence-points from meaningful persisted outcomes;
- competence: latest measured quality across existing development/growth/
  intelligence systems;
- architecture: explicit architecture_generation.

Architecture generation is never incremented merely because software version
changed.

Development stages D0-D6 follow the names and exit criteria in the source spec.
The engineering time thresholds use the upper bound of each stated early-stage
window as minimum exit time:

- D0: 30 days
- D1: 90 days
- D2: 180 days
- D3: 365 days
- D4: 730 days
- D5: 1825 days
- D6: open-ended

Time is necessary but never sufficient. Every exit criterion must have explicit,
non-expired passed evidence.

## Experience-age formula

Current `aishin-developmental-state-v1` evidence-points:

`meaningful autobiography + completed tasks + confirmed hypotheses +
 confirmed corrections + trusted strategies + mastered skills`

Autobiography entries below importance 0.5 do not add experience points. This
prevents ordinary boot/shutdown traffic from creating fake development.

## Competence-age formula

Current competence score is the arithmetic mean of latest persisted scores from:

- Development Metrics v2
- Long-Term Growth
- Cognitive Intelligence

for the runtime scopes that have measurements.

This is a technical maturity index, not an equivalent human age.

## AISHIN_NOW

Persistent current moment fields include:

- timestamp
- user/environment context
- current screen/project/scope
- latest scoped event
- focus
- active task
- expected next action
- last interaction
- last important event

Read-only GET paths do not create continuity snapshots.

## Inner time

AISHIN_INNER_TIME exposes:

- time_since_first_boot
- time_since_last_interaction
- time_since_skill_use
- time_since_important_event
- age_of_memory
- age_of_capability
- time_to_expected_event

## Autobiography

Autobiography is separate from ordinary message history. Foundation-level
episodes include:

- first boot
- runtime startup
- runtime shutdown
- developmental stage transition

Each episode preserves participants, context, change, lesson, importance,
confidence and memory links.

## Continuous self

A local SHA-256 continuity chain records:

- previous_state_hash
- snapshot type
- canonical payload
- identity hash
- persisted data-manifest hash

The identity hash comes from the canonical personality profile.

The data manifest covers critical persisted stores including runtime state,
AISHIN_NOW, memory/history, profile/relationship state, knowledge claims,
canonical facts and organism development/autobiography state.

### Clean continuity

At normal shutdown, all manifest-relevant changes happen before the shutdown
snapshot.

At next startup, validation occurs before ordinary startup mutations. A valid
shutdown manifest therefore provides a clean-continuity check.

### Status model

- genesis
- verified_clean_continuity
- active_session_unsealed
- unclean_gap
- chain_broken
- identity_changed_requires_review
- state_mismatch_after_clean_shutdown

An active running session is not incorrectly labelled an unclean gap.

### Threat boundary

This is a local integrity chain, not an externally anchored signature.

It can detect:

- modified snapshot payload/history;
- broken hash linkage;
- current canonical personality mismatch;
- current persisted manifest mismatch after a recorded clean shutdown.

It cannot prove detection of a perfectly coordinated rollback in which the
entire local database, including the continuity chain, is rolled back to a
self-consistent older copy. Detecting that reliably requires a future external
trust root or independently retained monotonic anchor.

The implementation exposes `external_trust_root=false` rather than claiming
stronger guarantees.

## Runtime ordering

FastAPI lifespan startup:

1. init_db
2. Digital Organism startup validation/session opening
3. existing Aishin engine startup
4. existing background workers

Shutdown:

1. stop heartbeat / continuous learning
2. await workers
3. seal Digital Organism shutdown session and snapshot

Direct Core Self-Check also opens and seals its own organism session so
diagnostics do not manufacture unclean gaps.

## Performance

Full manifest hashing is intentionally not performed on every chat turn or
Live Brain refresh.

Heavy validation occurs at startup or explicit continuity inspection.

Normal UI, prompt and request-trace reads use a lightweight continuity summary.

## APIs

Read-only:

- GET /api/assistant/organism
- GET /api/assistant/organism/now
- GET /api/assistant/organism/inner-time
- GET /api/assistant/organism/development
- GET /api/assistant/organism/autobiography
- GET /api/assistant/organism/continuity

Local-only mutations:

- POST /api/assistant/organism/now
- POST /api/assistant/organism/stage-evidence

## Live Brain

Live Brain v6 adds a Digital Organism surface showing:

- stage
- chronological age
- continuity status
- continuity snapshot count
- autobiography episode count

Backend counters additionally expose experience and competence age.

The existing 24-node execution topology is not inflated because this is a
persistent organism/state layer rather than a discrete reasoning phase.

## Validation contract

Release validation must prove:

- schema 27;
- application version 0.0.16;
- stable first_boot_timestamp across reads;
- nonnegative chronological age;
- valid D0-D6 stage value;
- stage eligibility contains time and evidence criteria;
- all AISHIN_INNER_TIME fields exist;
- autobiography is operational;
- read-only organism APIs do not create snapshots;
- continuity chain validates;
- snapshot payload tampering is detected;
- AISHIN_NOW context persists;
- mutation endpoints preserve local-only guard;
- Live Brain exposes Digital Organism;
- Core Self-Check opens and cleanly seals its diagnostic session;
- Ubuntu full runtime + headless Chrome pass;
- Windows full runtime + Aishin.bat --check-only pass.

## Deferred systems

Later stages should build on this foundation rather than bypass it:

- digital physiology
- interoception
- critical periods
- epigenome
- personality homeostasis
- cognitive scars
- breakthrough memory
- self curriculum
- digital dreaming
- personal ontology
- relationship continuity
- digital body schema
- external continuity trust anchor
