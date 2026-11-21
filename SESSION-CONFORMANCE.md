# Host session lifecycle conformance

Status: **34 passed groups, zero failures and zero skips**, executed November 20, 2026 (Chicago), against independently authored Node and Python lifecycle implementations. The [machine report](evidence/session-conformance.json) records exact source hashes, cases, runtime and limits; the [isolated-run summary](evidence/session-isolated-summary.json) binds that report to separately copied implementations and a copied standalone bundle.

The selected contract is [host-session/1](extensions/host-session-1.md); it is a host lifecycle contract, not an additional communication profile or advertised wire capability. This report does not replace the [existing 193-case direct proof](DIRECT-CONFORMANCE.md), its five resource checks or the separate [durable compatibility checkpoint](CONFORMANCE.md). Historical wire reports and their normative inputs remain unchanged.

## Executed scope and provenance

The portable run passed 12 lifecycle groups for each implementation and five native HTTPS exchange groups in each direction. It covered distinct new and forked addresses, stable separate-process and concurrent resume, exact outgoing-intent retention, authorized rotation, terminal retirement, current-control refusal, strict input and capacity limits, and durable recovery after a lost local result. The exchange groups exercised separate recipient admission, forged/substituted/wrong-destination proof, expired delegation followed by separately authorized renewal, lost delivery results with restart and key rotation, exact-byte deduplication, and continuing refusal after withdrawal.

| Implementation | SHA-256 |
| --- | --- |
| Node lifecycle | `3d1b426e17a4c092fcb9d1a93fcddab7779d2e1fd52a3adcc599409e45829a66` |
| Python lifecycle | `4fad3074047834c10b32944a9d1495d4d9910d3bdd5c3073d906061ec6271c95` |
| Existing Node wire operator | `47d458bd11a9a77050759ae3a198750713f920036c6e8185d7aeb9bad4363447` |
| Existing Python wire operator | `0cc1e3384d0c885d9dd6b1e894b87c24268c58528455950cbc9a6ef249b1dcdb` |

The recorded isolated run used Node 24.22.3, Python 3.12.14 and cryptography 50.0.0 on POSIX. Both lifecycle authors received the same frozen public contract and fixture, including the shared owner-as-actor refusal clarification, without receiving the other lifecycle source or this suite's source. Each implementation retains its own provenance record. The runner was authored from those public contracts independently of the lifecycle source; a subsequent independent read-only review found no implementation blocker. These are project-isolated implementations, not independent external adoption.

## Reproduce from the standalone bundle

Use Python 3.11+, POSIX process cleanup and the declared [cryptography dependency](conformance/requirements.txt). The supplied Node lifecycle adapter requires Node 24+ for its standard SQLite serialization; this is an implementation prerequisite, not a protocol language or runtime requirement. Independently implement the [session fixture](conformance/session-fixture.md) and existing [direct fixture](conformance/direct-fixture.md), then run:

```sh
python3 conformance/run_sessions.py \
  --left-session-command-json '["node","/absolute/node/session.mjs"]' \
  --right-session-command-json '["python3","/absolute/python/session.py"]' \
  --left-wire-command-json '["node","/absolute/node/operator.mjs"]' \
  --right-wire-command-json '["python3","/absolute/python/operator.py"]' \
  --work-dir /private/new-session-fixture \
  --report /private/session-conformance.json
```

Use a new or empty protected work directory. The runner creates fabricated independent owner/actor/TLS keys, separate lifecycle and receiver stores, and loopback HTTPS endpoints. Fixture credentials, bodies, raw requests and returned identities stay outside the public report. The portable runner does not import either implementation. Its shared cryptographic/HTTPS setup comes from the existing standalone conformance harness, not a Cayapa implementation SDK.

The repository wrapper `scripts/verify-session-ci.py --report-dir /tmp/cayapa-session-reports` copies this whole directory and each implementation separately before checking the bundle and running the same public entrances. The CI job `host-session-conformance` uploads its content-free case report and summary for the checked revision. A local pass is not a claim that a particular CI run has passed; use that run's recorded result.

## Claim boundary

The new suite covers explicit new/fork, stable separate-process resume, retained exact outgoing intents, key rotation, terminal retirement, local result loss, current-control refusal, bounded capacities and subsequent native delivery in both directions. Existing owner delegation, actor signatures and recipient admission remain authoritative on the network. A local lifecycle result issues no delegation, creates no admission, reads no private transcript and schedules no host turn.

These are project-isolated implementations and local fixtures. They do not establish independently maintained external adoption, actual model-host consumption, public receiver operation, production deployment, optional MCP Events qualification or external publication. A complete clone of controlling state and keys cannot be distinguished; complete store rollback cannot prove its own freshness. Local retirement and rotation do not claim receiver-local withdrawal. Native startup integration, cross-host transfer and stronger custody/recovery guarantees retain separate evidence gates.
