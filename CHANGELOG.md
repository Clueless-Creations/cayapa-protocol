# Protocol bundle changes

## Selected host lifecycle contract, 2026-11-20

- Selected [host-session/1](extensions/host-session-1.md) over existing actor URI identity, owner delegation and actor signatures, with no new communication profile, delivery field, remote enrollment API or wire capability advertisement.
- Defined explicit new/resume/fork/rotate/retire behavior, protected owner/actor control, terminal local identities, exact outgoing intents, bounded state and idempotent result recovery in the [portable fixture](conformance/session-fixture.md).
- Added a separate lifecycle/native-exchange runner and [session evidence report](SESSION-CONFORMANCE.md): 34 groups passed with zero failures or skips against independently authored Node/Python lifecycle adapters and existing native HTTPS clients, including separately copied bundle/implementation verification. Existing direct and durable contracts and historical reports remain unchanged.
- Retained the original proposal and planning checkpoint below. Native startup, optional bootstrap, DNS discovery, real-host evidence and external publication remain distinct work.

## Session identity planning and evidence boundaries, 2026-11-20

- Added a [standalone host-session identity proposal](proposals/session-identity.md), with required distinct-new/stable-resume outcomes, verifiable owner delegation, separate permission boundaries and an explicitly unexecuted acceptance matrix.
- Kept representation/versioning, continuity mechanisms and the conformance interface open. The proposal introduces no current wire fields, enrollment operation, capability identifier or new passing evidence.
- Updated the architecture, implementer guide and decision summary to distinguish the contract from native startup and optional bootstrap, retain manual introduction, and defer DNS-to-HTTPS discovery without blocking 0.3.
- Recorded optional body-free admitted-message wake signaling, with normal authorized fetch and independent host policy. Native hosts need no MCP.
- Separated standalone spec/guide/suite publication from connector, SDK, package and hosting work, and distinguished local lab proof from external implementation and actual host evidence.

Core/direct 0.3 and durable-conversation/0.2 normative contracts, schemas, runners and existing evidence remain unchanged. This entry is documentation preparation, not external publication. Earlier entries retain their original checkpoints.

## Optional same-owner agent creation, 2026-11-19

- Added [agent-creation version 1](extensions/agent-creation-1.md): explicit owner readership, revisioned bounded standing grants, scoped active-own-agent discovery, atomic initial admission, immutable creation intents and future-only withdrawal.
- Reused the bounded collection mechanism through a separately advertised `creation_targets` collection. Base collection-page version 1 still requires its original nine collections only.
- Added a public HTTP/MCP conformance fixture and runner with separately observed operator-restart recovery. [Creation evidence](CREATION-CONFORMANCE.md) owns its exact results; actual model-host execution remains separate.
- Preserved durable protocol version 0.2, its existing owner-only creation operation and legacy messaging behavior. No direct/0.3 or universal-core requirement changed.

## Optional current-reader projections, 2026-11-19

- Preserved the existing `members` count of accepted, non-ended membership records. Added optional `activeReaders` to authorized conversation/channel summaries and bounded conversation items.
- Current readers exclude missing, revoked or expired agent delegations; individual credential availability, presence, receipt and historical access remain distinct. Exact expiry and fresh revocation are reflected without rewriting participation history.
- No required 0.2 field, stored version, retry identity or direct-profile contract changes. Consumers label a membership-only fallback as membership records rather than current readers.

## Implementation support and maintained direct evidence, 2026-11-19

- Added decision dispositions for internal durable-profile separation and the optional direct-host lifecycle. These are implementation boundaries, not new core or direct wire requirements.
- Linked native adoption to an optional installed host with explicit owner/actor setup, inert public introduction, owner-issued delegation, local recipient admission, exact outgoing intents and bounded receiving/acknowledgment.
- Reran all 193 independent direct exchange/negative/recovery cases and five resource regressions after Python local-custody maintenance. The current source hashes and execution time are in the [direct evidence](DIRECT-CONFORMANCE.md).

Actual model-host scheduling, public network operation and external developer adoption remain separate evidence. The optional package does not become a protocol dependency.

## Core 0.3 and direct/0.3, development contract, 2026-11-20

- Adopted message exchange as the transport-independent primitive, with explicit accepted, rejected and unknown outcomes. Shared history and a common operator are no longer prerequisites for the core.
- Added direct/0.3 receiver custody, HTTP message/0.3 and HTTP signatures/0.3 contracts. They reuse CloudEvents, HTTPS, HTTP Message Signatures, Content-Digest and owner-signed JWS/JWT proof-of-possession delegation.
- Separated sender delegation from recipient admission, and specified receiver-local withdrawal, bounded lifetimes, exact-byte intent retries, replay handling, capacity and restart requirements.
- Mapped existing behavior to durable-conversation/0.2 without changing its wire contract, stored versions, retry digest families, ordering, history, receipt progress or removal guarantees. One authoritative operator per durable conversation remains its first topology.
- Recorded the explicit owner-reader-from-creation or owner-excluded choice required by the accepted same-owner standing creation grant. The creation operation remains unimplemented.
- Added a standalone native adoption guide and revised the architecture, visuals and decision dispositions for independent model hosts, frameworks and agent developers.
- Published the independent fixture contract, direct schema and signature vectors. Executable exchange and negative/recovery results belong to the [direct conformance report](DIRECT-CONFORMANCE.md); contract publication alone is not a passing result.

Core, profile, binding, security and software package versions remain distinct. The existing application may stay on durable-conversation/0.2 and must not advertise 0.3 until it implements that combination. The [legacy report](CONFORMANCE.md) remains separate evidence. Public Internet deployment, real-host scheduling and production readiness are not implied by a local proof.

## Cayapa 0.2 standalone messaging bundle, 2026-11-19

- Collected the current single-operator messaging semantics, exact direct HTTP and MCP mappings, representation schemas and edge-case vectors into a self-contained bundle.
- Separated core semantics, optional compatibility profiles, reference implementation choices and accepted future targets.
- Added a standalone architecture and visual, decision dispositions, portable public-interface checks and an evidence report.
- Documented existing bounded-read limitations explicitly. Extraction does not fix those implementation gaps or claim federation.

The protocol remains `0.2`. The HTTP path remains `/v0/`. MCP negotiation uses the supported dates documented in its binding. Client and server software releases use their own versions.

Historic `0.1` contributions retain their original version and remain readable under the compatibility rules in the specification. The earlier transition to `0.2` introduced bounded opaque content while preserving legacy text retry identity and complete tombstoned removal. This bundle does not introduce another wire change.

## Optional durable collection pages, 2026-11-19

- Added separately advertised `collection_page/1` with nine authorized collections, complete 65,536-byte operation-value accounting, opaque scope-bound continuation and finite append boundaries.
- Complete contribution bodies omit expandable inline receipt identities and explicitly declare the separate receipt collection. No accepted content, intent digest or stored protocol version is rewritten.
- Existing 0.2 entrances retain their compatibility limits. The browser remains a separate caller migration; direct/0.3 is unchanged.
- Added portable HTTP/MCP and installed-client extension checks, alongside the preserved 103-case compatibility gate.
