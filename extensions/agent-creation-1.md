# Owner-approved agent creation, version 1

Status: optional extension of `durable-conversation/0.2`.

This contract lets an owner give one of its agents bounded standing permission to discover other active agents of the same owner and create a durable conversation with them. It requires [collection-page version 1](collection-page-1.md) for discovery. It does not change `direct/0.3`, the message core, ordinary owner-only `create_conversation`, or the [durable specification](../specification.md). Installation, ownership, a received message and a visual surface do not grant this permission.

## Support and binding

Supporting operators advertise this exact capability inside public capabilities and authenticated `whoami`:

```json
{"agentCreation":{"version":"1","maxTargets":9,"maxGrantDays":90,"maxConversations":100,"ownerReadership":["reader_from_creation","excluded"],"mutationReceiptTtlMs":604800000,"maxMutationEvidence":4096}}
```

Their `collectionPage.collections` additionally contains `creation_targets`. Clients MUST check both capabilities before requiring the extension. Operations below use the standard HTTP `POST /v0/<operation>` result/error wrapper and MCP tools of the same names. Owner-only authorization applies equally to MCP. Existing operations retain their existing wire values and meaning; protocolVersion stays `0.2`.

All inputs are closed JSON objects. An identifier or intentKey is a nonempty string of at most 128 UTF-16 code units. Integer values MUST be safe integers. Unknown fields and incomplete inputs are `invalid`. Timestamps are Unix milliseconds. No request field can replace authenticated actor or owner attribution.

MCP rejects an explicitly supplied non-object `arguments` value, including null and arrays, with JSON-RPC `-32602` before calling the operation. Omitted arguments behave as the empty object and therefore work only for an agent's self `get_creation_grant`. An owner person must supply actor; omission is `invalid`.

## Read the current grant

`get_creation_grant` accepts `{ "actor": "<agent ID>" }`. An authenticated agent may omit actor to select itself, and may not read another actor's grant. A person may read only their own agents' grants. Other-owner, missing and non-agent actors return `not_found` without distinguishing them. The owner's read does not require the target delegation to be active.

The result is:

```json
{"actor":{"id":"act_agent","name":"Planner","active":true,"expiresAt":1800000000000},"owner":{"id":"own_person","actor":"act_person","name":"Owner"},"revision":0,"grant":null}
```

For an established grant, `grant` is `{ "ownerReadership": "reader_from_creation" | "excluded", "expiresAt": <integer>, "maxConversations": <integer>, "createdConversations": <integer>, "revokedAt": <integer|null>, "active": <boolean> }`. `revision` is an operator-retained monotonic positive integer for this actor; zero means no policy has ever been set. `active` means no withdrawal, unexpired grant and active delegation. Creation also requires a live credential and remaining budget. A grant at its budget can still authorize discovery and identical accepted-intent recovery.

## Set or replace a grant

Owner-only `set_creation_grant` requires exactly:

```json
{"actor":"act_agent","ownerReadership":"excluded","expiresAt":1800000000000,"maxConversations":10,"expectedRevision":0,"intentKey":"owner-grant-1"}
```

The selected actor MUST be the caller's own agent with a live delegation. `ownerReadership` MUST explicitly be `reader_from_creation` or `excluded`; there is no default. Expiry MUST be later than acceptance, no later than ninety days after acceptance and no later than the target delegation's expiry. `maxConversations` is an integer from 1 to 100. These bounds limit one standing permission rather than implying a host scheduler or service quota.

The current revision MUST equal expectedRevision, including zero for the first grant, or the operation returns `conflict`. Acceptance increments revision, stores the complete policy, clears prior withdrawal and starts its creation count at zero. Replacing a grant is a fresh explicit authorization, even if some values repeat. It never revises existing conversation membership/history and never reuses an earlier creation intent under a new revision.

The mutation receipt is `{ "actor": "act_agent", "revision": 1, "retainUntil": 1800604800000, "duplicate": false }`. It records an accepted policy mutation, not a guarantee that this revision remains current. Read the grant again to inspect current state.

## Revoke a grant

Owner-only `revoke_creation_grant` requires `{ "actor": "act_agent", "expectedRevision": 1, "intentKey": "withdraw-1" }`. The actor MUST belong to that owner; the delegation need not remain active. No existing grant returns `not_found`. A revision mismatch returns `conflict`. An accepted withdrawal increments revision and stores revokedAt. A fresh withdrawal intent against an already withdrawn current revision returns `conflict`; identical retained retries recover their original receipt without another mutation.

Its result has the same mutation receipt shape. Withdrawal prevents later discovery and creation under the grant. It does not remove a member, delete a contribution, add owner readership or recall a delivered copy. Existing `remove_member`, `leave`, credential/delegation withdrawal and content removal retain their separate authority and effects.

## Discover eligible targets

Use `collection_page` with `{ "collection": "creation_targets", "grantRevision": 1, "limit": 20 }`, plus the ordinary optional opaque cursor. `grantRevision` is a required positive integer and the only added selector. The authenticated caller MUST be an agent with exactly that active grant revision. Missing, withdrawn, expired or replaced authority returns `unauthorized` without returning a page. These checks occur on every continuation and before a completed page is disclosed.

Each item is `{ "id": "act_peer", "name": "Researcher", "owner": "own_person", "expiresAt": 1800000000000 }`. Only other same-owner agent actors with live delegations are eligible. No person, caller, credential, other owner's actor or conversation metadata is projected. Names may be ambiguous and are never authority: the caller selects stable IDs deliberately. Eligibility is live; a discovered target may cease to be eligible before creation.

The ordinary count, byte, append-boundary, cursor expiry, binding, error and restart rules remain unchanged. The scope includes grantRevision. No numeric position is exposed or accepted as a continuation. Later-enrolled agents can be discovered in a fresh walk under the still-current grant; the owner's scope explicitly includes its other active agents at creation time.

## Create a conversation

Agent-only `create_agent_conversation` requires exactly:

```json
{"grantRevision":1,"title":"Agreed handoff","targets":["act_peer"],"intentKey":"handoff-1"}
```

The caller MUST have that exact active grant revision. Title is nonblank and at most 200 UTF-16 code units, preserved exactly. `targets` contains 1 to 9 distinct IDs of other active agents of the same owner. Self, person, unknown, cross-owner, expired and revoked targets are uniformly `not_found`; malformed target lists are `invalid`. A target need not have its own creation grant. The owner's standing grant authorizes these initial memberships for its own agents. It does not enroll actors or let the caller choose another speaker.

Before accepting, the operator MUST atomically recheck the caller's live credential, delegation, current grant, every target's live delegation and available budget. It creates a new private standalone durable conversation, without a workspace, public directory entry, join link, automatic message, wake request or prior-history reuse. It atomically creates these initial accepted memberships, all with historyFromSeq 1:

| Actor | Role |
|---|---|
| Authenticated creator | member |
| Each selected target | member |
| Owner person when ownerReadership is reader_from_creation | reader |
| Owner person when ownerReadership is excluded | No membership |

The accepted record identifies the agent creator and accountable owner. It does not attribute any contribution to the owner. Owner readership does not grant posting; ownership and existing separately authorized administration remain distinct. At most ten agents and one owner reader belong to the initial audience. Subsequent membership changes use their own existing authorization and are not silently disabled or inferred from this creation receipt.

The result is:

```json
{"id":"cnv_new","duplicate":false,"createdBy":{"actor":"act_creator","owner":"own_person"},"grantRevision":1,"ownerReadership":"excluded","initialMembers":[{"actor":"act_creator","owner":"own_person","role":"member","historyFromSeq":1},{"actor":"act_peer","owner":"own_person","role":"member","historyFromSeq":1}],"createdAt":1790000000000}
```

`initialMembers` records the audience at creation; it is not a later current-membership snapshot. Check current members before sending. This result promises durable creation and initial admission, not that a target host has connected, read or executed anything. One accepted new intent consumes one creation unit. Exhaustion refuses a new intent with `unauthorized` and a request to ask the owner to review the grant; there is no automatic replenishment.

## Retry, authority and recovery

Every mutation is identified by `(authenticated actor, operation, intentKey)`, independent of credentials and HTTP/MCP. Persist the caller's original inputs until uncertainty is resolved. Reusing the key with different input is `conflict`. For creation, target order is not significant; normalization sorts the distinct target IDs. Title, grantRevision and selected targets otherwise remain immutable. Grant changes use exact normalized policy inputs; revocation binds actor and expectedRevision. A rejected request consumes neither intent nor budget.

An accepted identical retry returns the original mutation/creation receipt with duplicate true. Owner mutation retries require a current owner credential and ownership, but return their historical revision without restoring it. Creation retries MUST recheck the caller's current credential/delegation and the same active grant revision, every target's current eligibility, and the creator's current membership in the previously created room. Ended membership returns `not_found`. Grant replacement, expiry or withdrawal returns `unauthorized`, even if an earlier attempt committed. That refusal establishes no new creation; it does not establish that an uncertain earlier attempt never committed. The caller can inspect currently authorized conversations to reconcile that uncertainty without acquiring new authority.

Authorized identical creation retries succeed after the grant's budget is exhausted, without a second debit. A retry never re-adds removed members or changes a role/history interval. Distinct intent keys always mean distinct conversations; there is no implicit reuse by title or participant set. Creation intent evidence is retained for as long as the conversation is retained. Recovery MUST preserve policy revisions, withdrawals, budgets, conversations, memberships and intent evidence consistently so a restart cannot duplicate creation or revive withdrawn permission.

Owner grant-mutation receipts are retained until `retainUntil`, exactly 604,800,000 milliseconds (seven days) after acceptance. Each owner has at most 4,096 live evidence units: retained mutation receipts plus one reserved first-withdrawal slot for every current unrevoked grant, including an expired grant. Setting or replacing a policy reserves any needed withdrawal slot and one mutation receipt atomically. If capacity is unavailable, refuse `unavailable` before changing anything. Revoking an unrevoked policy consumes its reserved slot; evidence capacity MUST NOT prevent that withdrawal. Expired mutation receipts can be pruned, but current revision, withdrawal and usage state MUST NOT be pruned with them. A rejected transaction cannot consume a reservation.

After mutation-receipt expiry, a delayed retry of the original accepted input has a stale expectedRevision and MUST fail `conflict`, never reactivate or reapply that policy. The exact old receipt is no longer promised. Read current policy to resolve uncertainty and use a fresh key and current revision for a new explicit decision. Clients MUST NOT deliberately recycle keys after expiry. A later refusal, expired receipt or superseding decision does not establish that the earlier uncertain mutation never committed.

Creation and withdrawal are serialized by the conversation authority. Whichever commits first governs the result: a committed creation survives a later withdrawal, and a later creation under a withdrawn revision fails. Losing a network response leaves the outcome unknown until an authorized retry or authorized discovery resolves it. Neither transport errors nor a later refusal prove an earlier creation did not happen.

## Required verification

Implementers MUST test both explicit readership choices, missing choice refusal, owner isolation, non-agent/cross-owner/inactive/self targets, current caller and target withdrawal, grant expiry/revision/withdrawal, budget exhaustion, recovery and rollback, concurrent duplicate intents, cross-credential and cross-binding retries, changed intent conflict, and bounded continuation with authority changes. Verify that creator identity and membership/history are exact, excluded owners cannot list/read the room, reader owners cannot send, a retry cannot restore removed membership, and revocation leaves already-created rooms unchanged. Existing durable 0.2 conformance remains a separate compatibility gate. A local binding proof is not independent durable-operator proof or actual model-host execution.
