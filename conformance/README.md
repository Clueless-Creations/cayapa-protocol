# Portable conformance observations

## Optional host lifecycle suite

The [host-session/1 contract](../extensions/host-session-1.md), [session fixture](session-fixture.md) and [session report](../SESSION-CONFORMANCE.md) define a separate lifecycle suite. `run_sessions.py` accepts independent left/right session and wire command vectors, a new private work directory and a report path. It exercises local authorized lifecycle controls and then existing native Direct/0.3 exchange over verified loopback HTTPS. See the report for the complete command and actual results.

This is optional test integration, not a required production CLI or public enrollment API. Its counts remain separate from direct wire and durable conformance. A lifecycle result grants no admission, remote read, wake or action authority; independently maintained external implementations and real model hosts require their own evidence.

## Choose the profile suite

| Profile | Runner and fixture | Evidence |
| --- | --- | --- |
| `direct/0.3` | [run_direct.py](run_direct.py), [independent-operator fixture](direct-fixture.md), [cryptography dependency](requirements.txt) | [Independent operators and recovery](../DIRECT-CONFORMANCE.md) |
| `durable-conversation/0.2` | [run.py](run.py), the fabricated membership/history fixture described below | [Existing 0.2 conformance](../CONFORMANCE.md) |

The direct suite starts two independent native senders/receivers with separate owner and actor keys, stores, and HTTPS endpoints. It exercises both directions, public negative cases, withdrawal, key rotation, response loss and restart. It requires POSIX and Python 3.11+ for fixture orchestration, not a Cayapa SDK or service. See [native implementation guidance](../IMPLEMENTING.md) for the standalone invocation. Its local consumer inspection is not a network history operation. Do not combine its results with the 0.2 count or claim that either profile proves the other.

Run `python3 conformance/check-direct-resources.py` for five focused direct-runner capture and process-group regressions. They cover successful-wrapper descendants, oversized output, a stalled adapter that ignores termination, normal server shutdown and invalid readiness. Their counts are reported separately from message interoperability. Fixture descendants must remain in the created process group; the harness is not a sandbox for hostile executables.

## Durable-conversation/0.2 suite

The optional [agent-creation version 1 fixture](creation-fixture.md) and `run_creation.py` exercise explicit owner grants, bounded own-agent discovery, both readership choices, common HTTP/MCP creation and restart recovery separately from the legacy messaging gate. Its ten exercise groups and three recovery groups require fabricated owner control credentials and an actual separately observed restart. Base collection conformance does not require this extension.

`run.py` exercises the [Cayapa 0.2 specification](../specification.md), [direct HTTP binding](../bindings/http.md), and optional [MCP binding](../bindings/mcp.md) against a running operator. It uses Python's standard library and public protocol requests. It imports no operator, storage layer, worker runtime, SDK, or installed client implementation.

The runner performs real writes, reads, acknowledgments, and author retractions using explicitly provisioned, fabricated participants. Its private fixture file is the boundary between protocol verification and operator-specific provisioning. No administrative endpoint or owner credential is required by the runner. Provisioning is deliberately outside this directory because independently implemented operators can create the same authority and history conditions through different control planes.

## Run from a standalone protocol checkout

Requirements: Python 3.10 or later, a running operator implementing the HTTP profile, and a fresh disposable fixture file following [the example](fixture.example.json). The example contains placeholders and cannot authenticate. Keep the populated file outside a source repository with permissions restricted to its owner.

From the root of this protocol directory:

```bash
python3 conformance/run.py \
  --fixture /tmp/cayapa-fixture.json \
  --report /tmp/cayapa-conformance.json
```

This command needs only the protocol directory, its vectors, and network access to the explicitly configured fixture operator. It does not discover a production endpoint, bootstrap users, install a client, enable wake delivery, or contact an external agent. Network deployments use HTTPS; HTTP is accepted only for loopback fixtures. Redirects are refused so bearer credentials are never forwarded to another origin. The harness ignores environment proxy configuration and connects directly to the supplied origin.

HTTP responses and subprocess output are collected with a 2 MiB safety cap, allowing one additional byte to detect overflow. This is a harness implementation limit, not a protocol response-size promise. An HTTP watchdog interrupts the connected socket at the transfer deadline, including during response headers or a slowly delivered body; successive bytes do not reset that deadline. Platform DNS resolution and connection establishment before a socket becomes available still follow the resolver and connection timeout behavior. Subprocess output is read incrementally with the same cap and a wall deadline, followed by terminate, kill if necessary, and wait cleanup. Cleanup has its own short bounded allowance.

Use a newly provisioned fixture for each run. Its conversations must be dedicated to this run, with no concurrent writers or pre-spent quotas. Reusing a fixture can exceed the specified per-actor send quota, accumulate unrelated records, or invalidate sequence assumptions. Expired or incomplete fixtures produce failures rather than being silently replenished.

The result contains one entry per executed assertion group or content vector. Exit status is 0 when every executed case passes, 1 when any case fails, and 2 when configuration or report writing fails. An omitted independent client is explicitly reported as skipped. Set `--require-client` when independent-client evidence is a release gate.

## Resource-limit regression checks

From a standalone protocol checkout, run:

```bash
python3 conformance/check-resources.py
```

The standard-library script starts its own loopback HTTP fixture and disposable driver processes. Its eight checks cover normal HTTP, successful and unsuccessful driver results, oversized HTTP and process output, a stalled process, slowly delivered HTTP headers, and a slowly delivered HTTP body. It verifies bounded capture, wall deadlines, and process cleanup without a Cayapa operator, installed client, or real credential. Noisy fixtures produce a finite amount above the safety cap so a regression can fail without unbounded test output. A failed assertion exits nonzero; a successful run prints a content-free JSON report with the runner hash and observations.

## Fixture contract

The JSON file has `fixtureVersion: 1`, `disposable: true`, `baseUrl`, `bindings`, `credentials`, `conversations`, and `history`. `bindings` must contain `http` and may also contain `mcp`. Supply an optional full hexadecimal `operatorRevision` to identify the operator source being exercised; deployment provenance still belongs in the accompanying evidence report.

The credentials represent these conditions:

| Key | Required authority at the start of the run |
| --- | --- |
| `a` | Live actor A with writable membership and full history in `main`, `bounds`, and `vectors` |
| `b` | A different live actor B with the same three memberships |
| `b2` | A second, separately issued live credential for actor B; it has its own receipt state |
| `reader` | A separate live actor with a `reader` membership and full history in `main` |
| `outsider` | A separate live actor without membership in `main` |
| `removed` | A separate live actor whose accepted `main` membership has already ended; its credential remains valid |
| `revoked` | A credential that has already been revoked after previously having access to `main` |
| `late` | A separate live actor with writable history-limited membership in the separate `history.conversation` |

The runner discovers actor and connection IDs through `whoami`, verifies that A and B differ, and verifies that B and B2 are distinct connections for the same actor. These are fixture preconditions, not identity enrollment operations. An operator may use one or several fabricated owners; the runner does not itself prove cross-owner invitation approval.

The three `conversations` values are distinct, already accepted exchange contexts:

| Key | Purpose |
| --- | --- |
| `main` | Cross-entrance exchange, authority, intent, cursor, receipt, and removal observations |
| `bounds` | A second cursor space and complete-item pagination under the item-byte budget |
| `vectors` | Literal positive and negative [content vectors](../vectors/README.md), isolated from other send quotas |

For `history`, provision a separate conversation as follows:

1. Accept a contribution before granting `late` access. Put its ID in `hiddenContribution`.
2. Grant `late` writable membership with history beginning after that contribution.
3. With an authorized actor that can see the old contribution, accept another contribution whose `replyTo` and `corrects` both point to it. Ensure the correction satisfies the same-owner rule.
4. Put the new contribution's ID in `visibleContribution` and its conversation sequence in `visibleSeq`.

The runner then observes that `late` can fetch the newer contribution, cannot fetch or acknowledge the old one, receives hidden relationship flags without the old identifiers, and cannot use a hidden target in a send. A corrected send under the same previously rejected intent key must succeed.

Revocation and membership removal happen **before** the portable runner starts. Their current effects are observed through both entrances. A separate operator-specific setup report can demonstrate successful access before each transition and denial afterward; the portable report does not invent that timing evidence.

## Independently installed client driver

An independently written client can participate without being imported into the runner. Supply an executable and its arguments as a JSON array:

```bash
python3 conformance/run.py \
  --fixture /tmp/cayapa-fixture.json \
  --report /tmp/cayapa-conformance.json \
  --client-command-json '["/tmp/cayapa-venv/bin/cayapa", "call"]' \
  --require-client
```

The runner starts a new process for each operation and supplies:

| Interface | Contract |
| --- | --- |
| Environment | `CAYAPA_URL` is the fixture origin; `CAYAPA_TOKEN` is the current fabricated actor's raw credential |
| Standard input | One UTF-8 JSON object: `{"operation":"send","arguments":{...}}` |
| Standard output | One normalized result: `{"ok":true,"value":...}` or `{"ok":false,"error":{"code":...,"message":...,"retryable":...}}`; additional wrapper fields are allowed |
| Exit status | 0 for success; 0 or 1 for an operator-declared semantic failure |
| Process lifetime | A bounded foreground request; no interactive prompt or background installation |

For example, input `{"operation":"whoami","arguments":{}}` must authenticate the provided credential and return the identity value inside a successful wrapper. The normalized form is the same as the HTTP binding. A client using another entrance may implement a small adapter to produce it. This subprocess contract is test tooling, not a new Cayapa wire binding or an agent installation standard.

The runner uses an argv array directly, with no shell expansion. It supplies only a small environment allowlist plus the two Cayapa variables. Standard error is withheld from the report because client failures may contain credentials or private response data. A nonzero result still has its standard-output JSON parsed. A local configuration or transport failure must remain a failed observation; it must not be reclassified as an expected operator refusal.

With a driver, the runner sends both Unicode opaque content and binary opaque content from the external client to the MCP participant, then sends both in the other direction. It compares entire envelopes, attribution, decoded bytes, reply relationships, same-intent retries, changed-intent refusal, outsider refusal, and revoked-credential refusal. Separate external-client groups repeat the cursor and receipt, authority, history, and retraction cases through the installed executable itself. They include bounded continuation after restarting the process, separate unread state for two credentials of the same actor, no automatic acknowledgment on fetch, reader restrictions, hidden relationship projection, and no resurrection after retraction. If MCP was omitted from the fixture, the peer uses direct HTTP and the report names that narrower configuration.

Every external-client operation starts a fresh process. Passing continuation and same-intent retry after that restart demonstrates operation without hidden process-local state. It does not simulate a dropped connection during acceptance or establish a broader network fault-tolerance claim.

Independent authorship, a clean installation, and implementation provenance cannot be inferred from a subprocess boundary. The accompanying evidence must identify how the client was implemented and installed. Two executables sharing one client library do not establish independent implementations.

## What is checked

| Area | Positive observation | Expected refusal or failure boundary |
| --- | --- | --- |
| Identity and discovery | Authenticated actor/owner, independent connections, public content capability, MCP negotiation and tool discovery | Revoked credential; unknown method/tool/operation |
| Body preservation | Exact Unicode without normalization, arbitrary binary bytes, sender fallback, compatibility text, attributed replies | Unknown or mixed body fields; invalid type, encoding, base64, Unicode, fallback, or size vectors |
| Intent identity | Equivalent retry returns the same ID and sequence across entrances, including after retraction | Changed content, fallback, media type, body family, or conversation conflicts; rejected inputs do not consume a fresh key |
| Authority | Reader can read and acknowledge; authorized members can communicate | Reader writes, outsider reads/writes/receipts/retraction, pre-removed membership, pre-revoked credential |
| History | Granted history remains readable with truthful hidden-link flags | Old content and old relationship IDs stay hidden; inaccessible targets cannot be referenced or acknowledged |
| Cursors | Count-limited continuation, a resumed second connection, distinct conversation and operator cursor spaces | No duplicate continuation, no implicit shared progress, no self-authored inbox delivery, no invented advancement on empty results |
| Receipts | Explicit, repeatable receipt; credential-scoped unread; actor-level projection; replay after receipt | No receipt on read; no invented `executed` stage; empty or oversized batches rejected |
| Retraction | Entire opaque envelope and fallback cleared, legacy body cleared, tombstone and visible relationships retained | Another member cannot retract; repeat and retry cannot restore content |
| Binding bounds | Exactly 65,536 raw request bytes accepted; exact envelope boundary represented in vectors | 65,537 raw request bytes rejected; malformed UTF-8/JSON and unsupported methods rejected |
| Contribution pages | Complete large items, byte omission signal, continuation without loss or truncation | No claim of a hard 65,536-byte wire-response maximum |

Each supplied content vector is sent over HTTP and, when selected, MCP. Accepted vectors are read back through the other entrance. Negative vectors are expected to fail with `invalid`; they count as passes only when the operator refuses them. A vector file with more than 30 accepted cases per actor requires a new fixture arrangement instead of silently violating the current quota.

## Reports and claim limits

Reports include protocol version, optional operator revision, executed bindings, case outcomes, observation time, and hashes of the portable specification, bindings, schemas, vectors, and runner. They contain no tokens, operator URL, actor or contribution identifiers, message bodies, raw responses, or subprocess output. Failure messages are deliberately content-free. This makes a report suitable for review without publishing its private fixture.

The current specification documents an item-byte budget with a first-item exception, wrapper overhead outside that budget, unbounded conversation discovery, and member-list omission without continuation. The runner verifies real content/request boundaries and ordinary large-item continuation. It explicitly declines a hard response-wire-bound claim; the known limitation is not disguised as a passing hard-bound test.

Passing observations establish the behavior of the named clients and entrances against the specific tested operator and fixture. They do not establish federation, two independent servers, interactive OAuth in a particular host, a native integration in an untested agent, an autonomous polling loop, wake delivery, capability rental, payments, attachment transfer, or exactly-once execution. A user's two real agents remain a separate installation and consented acceptance exercise.

## Optional collection-page version 1

Run `python3 conformance/run_collections.py --fixture /private/collections-fixture.json --report /tmp/collections-report.json --client-command-json '["/absolute/installed/cayapa","call"]'` from the extracted bundle. This run requires HTTP, MCP and a separately installed client, and must report **11 passed, 0 failed, 0 skipped**. It supplements the existing 103-case gate; it does not replace it.

The private fixture follows the existing version-1 shape, with two additional entries: `credentials.owner` is a fabricated owner-person credential whose agents are the existing roles, and `conversations.collections` is a fresh empty conversation containing that owner and actors A/B. The owner must have at least seven agents and B two distinct credentials. Provision at least one revoked and one non-revoked fabricated subscription for B before running; configure no endpoint or destination secret. Existing withheld-history and pre-revoked fixtures remain required. The runner only reads owner collections; it does not execute owner-side provisioning or revocation operations. The reference-only provisioner can create the separate private file with `--collections-output`; its original fixture still contains no owner credential. Never publish either fixture.

The extension run sends three fabricated contributions, claims one receipt, and uses public HTTP/MCP plus a fresh subprocess for each installed-client call. It covers all nine advertised collections, byte continuation for complete escaped bodies, finite append boundaries, credential-bound opaque cursors, owner/outsider refusal, withheld history, pre-revoked authority, separated receipt claims, current-credential unread filtering, unsupported input and measured wrapper budgets. Deep archived history, live owner grant changes, restart and expiry are separately exercised by the reference operation tests. These distinctions remain explicit in its content-free report.
