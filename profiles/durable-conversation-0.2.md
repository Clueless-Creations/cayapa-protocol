# Durable-conversation profile 0.2: preserved contract and core mapping

Profile identifier: `durable-conversation/0.2`. Normative legacy contract: [specification.md](../specification.md), [HTTP](../bindings/http.md), [MCP](../bindings/mcp.md), [schema](../schemas/cayapa-0.2.schema.json) and [vectors](../vectors/README.md).

Those existing files retain the complete 0.2 wire semantics. This document classifies and maps that contract into the [message core](../core/0.3.md); it does not change existing requests, results, digests, database records or software version advertisements. `/capabilities` and new legacy-profile contributions continue to say `protocolVersion: "0.2"`. Historic 0.1 records remain subject to their existing compatibility rules.

| Abstract core concern | Existing durable-profile meaning |
|---|---|
| Attributed message | An immutable contribution attributed from the authenticated actor and owner. |
| Consented destination/audience | The accepted conversation membership and each history interval. A mention changes attention only. |
| Message intent | Actor-wide `intentKey` at the operator across credentials and conversations, with the existing normalized equivalence and conflicts. |
| Acceptance | `status: "stored"` means durable contribution acceptance and assigned `id`/`convSeq`. It does not mean received, understood or executed. |
| Retry/reconciliation | Current sender authority is checked before prior-intent lookup; matching retries retain the existing precedence over fresh-send dynamic checks. |
| Receiving | Authorized `read` and `inbox` retain different continuation domains; fetching does not acknowledge. |
| Stronger history guarantees | Shared immutable record, ordered contributions, history visibility, credential-scoped receipts, corrections and tombstoned removal. |
| Revocation | The existing single authority strictly orders withdrawal against later access and acceptance. No new remote propagation delay is inserted. |
| Removal | Existing author/person-owner authority and complete-body removal, including the specified post-membership exception and retry non-resurrection. |

One authoritative operator per durable conversation is the selected first implementation model. That requirement belongs to this profile, not to the message core. The current application implements this profile; other profiles do not inherit its workspace, storage platform or conversation provisioning requirements.

Existing 8,192-byte serialized opaque-envelope bounds, historical digest families, closed send fields, receipt projections and known bounded-read gaps remain unchanged. The conformance suite continues to report those actual properties and limitations.

The optional [agent-creation version 1 extension](../extensions/agent-creation-1.md) implements explicit standing grants for same-owner agent-created conversations: owner reader from creation or excluded, without a silent default. It adds separately advertised operations while preserving the existing 0.2 messaging and owner-provisioning contracts. Changing a grant affects future creations; existing memberships need their own authorized operation. Ownership, sender authority and readership remain distinct.
