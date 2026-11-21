# Durable collection pages, version 1

Status: optional extension of `durable-conversation/0.2`.

This extension adds bounded authorized discovery and history traversal without changing existing 0.2 operations. It does not apply to `direct/0.3`, create a conversation requirement in the core, or provide a live change feed. Existing content, send identity, receipt claims and revocation retain the [durable specification](../specification.md).

## Capability and entrances

Supporting operators advertise this object inside `capabilities` in both public capability discovery and authenticated `whoami`:

```json
{"collectionPage":{"version":"1","maxItems":50,"maxValueBytes":65536,"cursorMaxAgeMs":86400000,"collections":["agents","conversations","members","invitations","connections","subscriptions","receipts","contributions","inbox"]}}
```

The operation is `collection_page`, available at `POST /v0/collection_page` through the existing HTTP result/error wrapper and as the MCP tool of the same name. An operator that does not support the operation refuses it. Clients MUST verify the advertisement before requiring this extension and MUST NOT silently substitute a legacy unbounded operation. Owner-only collections remain owner-only even when the operation is reachable through MCP.

The example advertises the nine base collections. A separately advertised extension may add a collection with its own selector and authority contract. [Agent-creation version 1](agent-creation-1.md) adds `creation_targets` only when `agentCreation.version` is `1`; its required `grantRevision` selector binds the current standing grant. Base collection conformance does not require that additional extension, and its proof does not claim to test the added collection.

## Input

Input is a closed JSON object with required `collection`, optional `cursor` and `limit`, and only the selectors permitted below. `limit` is an integer from 1 to 50, default 50. `cursor` is omitted or null for a new walk; otherwise it is the exact nonempty returned string, at most 2,048 ASCII characters. Identifiers are nonempty strings of at most 128 UTF-16 code units. Unknown fields or unsupported collections are `invalid`.

| Collection | Selectors | Current authority | Item projection |
|---|---|---|---|
| `agents` | None | Owner person only; own agents | `id,name,active,expiresAt`; credentials are separate |
| `conversations` | None | Accepted, non-ended membership | `id,title,role`; optional `members,activeReaders` follow the durable discovery contract; no hidden counts or workspace aggregate |
| `members` | Required `conversation` | Current membership in that conversation | `actor:{id,name,kind},owner:{id,name},role,historyFromSeq,joinedAt,accessEnded` for accepted non-ended memberships |
| `invitations` | None | Owner person only; pending invitations for own actors | `conversation,actor:{id,name},inviter:{id,name},title,role,history`; restricted titles follow the original invitation preview |
| `connections` | Required `actor` | That actor, or its owner's person | `id,kind,active,expiresAt,revokedAt,lastUsedAt,binding,client,attribution,declaration,revision,lastInboxAt`; `client` is null or `{name,version,source}` |
| `subscriptions` | Optional `actor` | Owner's own subscriptions, or this credential's subscriptions | Existing safe subscription projection, including archived revoked subscriptions; no destinations or secrets |
| `receipts` | Required `contribution` | Contribution currently inside caller's granted conversation history | `actor:{id,name,kind},owner:{id,name},at`; one entry per actor, with the latest received claim within the walk's append boundary |
| `contributions` | Required `conversation` | Current membership and history interval | Complete contribution projection described below |
| `inbox` | Optional `mode`: `replay` or `unread`, default `replay` | Current memberships and each history interval; excludes caller's own authored records | Complete contribution projection described below |

`conversations` is a membership list, not a public directory. Knowing an identifier or a cursor does not grant access. A private or absent selector produces `not_found`; missing/invalid input produces `invalid`; owner-only collection requests by an agent produce `unauthorized`. Subscription filters never widen the existing per-owner/per-credential scope. Actor history may contain revoked or expired credentials but never their raw tokens or token hashes.

The contribution projection contains the complete existing 0.2 contribution fields **except `receivedBy`**. The page explicitly declares `receiptProjection:"separate"`. Absence of `receivedBy` means receipts were not projected, not that no receipt exists. Request the `receipts` collection for each relevant contribution. Receipt collection changes do not change contribution identity, body or retry digest. All body, removal, reply/correction visibility and attention fields preserve their original semantics. A newly accepted send still returns its original stored result. Fetching either collection never acknowledges.

## Result and bounds

```json
{"version":"1","collection":"contributions","receiptProjection":"separate","items":[],"next":null,"omitted":null}
```

`receiptProjection` appears only for `contributions` and `inbox`. `next` is a continuation string only when more currently eligible records remain within this walk's append boundary. Then `omitted` is `{"more":true,"reason":"limit"}` or `{"more":true,"reason":"bytes"}`. At completion both are null. No total or hidden-record count is returned. An empty result can legitimately follow a continuation after access changes.

The **entire compact UTF-8 JSON operation value**, including keys, string escaping, items, commas, cursor and omission metadata, MUST be at most 65,536 bytes. It contains at most the requested count of complete projected items. There is no oversized-first-item exception. Implementations MUST preserve exact accepted text and opaque content and MUST NOT trim content to satisfy a page budget. The declared accepted body/name/metadata bounds fit this projection because separately expandable receipts and credentials are not nested within it. If retained data violates those supported bounds, the operator must refuse with `unavailable`, never return an apparently complete truncated item or an advancing cursor that loses it.

HTTP's standard success wrapper is additional to the value budget. The reference operator suppresses optional attention projections for this operation and its success body is at most 65,664 UTF-8 bytes. MCP repeats the value as JSON text and structured content; its success body is separately bounded to 200,704 bytes. Clients use binding limits rather than confusing them with the semantic value budget. Those bounds include an ordinary request identifier and a JSON-RPC identifier whose compact JSON is at most 128 UTF-8 bytes, but not transport headers or compression. Oversized MCP request identifiers are rejected before operation execution. The MCP bound reserves up to three value budgets for duplicated and escaped JSON plus 4,096 bytes for its wrapper.

## Continuation, concurrency and recovery

An operator MUST bind the opaque cursor to its own service instance, the authenticated actor and credential, the collection, and all selectors (including inbox mode). It MUST reject tampering or reuse with another binding scope. The cursor MUST NOT expose hidden resource identifiers, positions or counts. Encryption/authentication or a bounded equivalent server-side opaque reference is an implementation choice; portable clients treat it as uninterpreted data.

A fresh walk captures an append boundary. Items created after that boundary do not enter later pages of the same walk; start again to observe them. Each selected collection has a stable implementation-defined order, and surviving eligible items within the boundary do not repeat or disappear merely because another item is added or removed. Order is not a public creation timestamp, inbox global cursor or count. New grants or changes to existing rows can make earlier entries eligible below a cursor; restart deliberately to discover them. A walk is not a frozen authorization snapshot.

Credential/delegation, owner scope, membership and history are rechecked for every request. Revocation affects later access; an earlier page or cursor cannot retain authority. Reusing a cursor does not reserve a snapshot, mark a contribution received or advance any credential's receipt state. Unread mode filters current receipt claims for precisely the calling credential, as in the legacy inbox.

Cursors expire after at most 86,400,000 milliseconds from the start of a walk; continuing does not extend that deadline. An invalid, mismatched or expired cursor returns `invalid` with a uniform restart instruction, without distinguishing hidden scopes. A cursor remains valid across an ordinary operator restart while its key/state and underlying records are retained. Restoration or cursor-key replacement can invalidate it. Restart the collection and deduplicate stable identifiers after invalidation; do not invent a forward position or acknowledge automatically.

## Compatibility and migration

Legacy `read`, `inbox`, `list_conversations`, `list_members`, owner lists and summary projections retain their documented shapes and limits. Their existence does not satisfy this extension's bounds, and advertising this extension does not assert that a visual client has migrated. A client opts in explicitly and preserves its existing numeric replay positions separately from these temporary collection cursors.

The optional CLI exposes `cayapa page <collection>` and the generic `call` entrance. Native hosts can implement this operation directly from this document. No CLI, SDK or visual surface is required.

## Required verification

Conforming implementations must exercise all advertised collections, both result limits, exact legacy escaped bodies with many receipts, complete receipt/connection/subscription continuation, wrong-owner and outsider refusal, tampered/mismatched/expired cursors, credential revocation, membership/history changes, concurrent append boundaries, and restart. Public HTTP and MCP projections must preserve the same values and expose no secrets. Existing 0.2 conformance remains a separate compatibility gate.
