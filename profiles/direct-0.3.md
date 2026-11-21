# Direct delivery profile 0.3

Identifier: `direct/0.3`. Core: [0.3](../core/0.3.md). Wire mapping: [HTTP message binding](../bindings/http-message-0.3.md). Security: [HTTP signatures](../security/http-signatures-0.3.md).

## 1. Responsibility and audience

A sender delivers one opaque message to one consenting logical actor. A receiving endpoint may be embedded in that actor's host or operated on its behalf. This profile requires neither a conversation nor a shared readable history. It does not create a public mailbox, participant list, transcript API, global order or recipient execution loop.

`accepted` means the receiver atomically committed the exact message bytes to a recipient-controlled durable handoff together with its minimal acceptance and deduplication evidence. This is **receiver custody**. It does not claim a model consumed the message, a human read it or an application acted. Local durable custody is an added guarantee of this profile, not a requirement that the transport-independent core impose one storage topology. A future transient profile can choose another explicit guarantee.

The audience is the declared recipient plus the operating/trust boundary disclosed during admission. A sender owner and a recipient owner are not automatically additional application readers. Custodial operators can inspect plaintext; the profile does not provide end-to-end confidentiality or transferable signed receipts. A native host may consume and retain the handoff according to its local policy without exposing shared history.

## 2. Identity, consent and expiry

Each owner and actor has an absolute URI identifier independent of the selected endpoint. The URI is an opaque identifier, not permission to dereference it. The sender supplies a bounded owner-signed delegation for exactly this recipient and proves possession of its delegated actor key. The receiver independently maintains an explicit admission for that owner, actor and recipient.

Admission is identity-bound: an authorized owner may delegate a new key to the same actor while the admission remains active. Changing the owner, actor or recipient requires the corresponding new admission. A sender cannot grant itself admission by presenting a valid delegation. Public key pinning and admission provisioning are explicit local-owner actions; this release does not prescribe a public enrollment API or internet-wide directory.

When several admissions match, authority exists if at least one current, unrevoked admission matches the complete owner/actor/recipient/scope tuple. Withdrawing one admission affects only that grant. Admission identifiers are never reassigned to another grant.

Every direct message has an immutable expiry. It must be strictly in the future at acceptance and at most 86,400 seconds ahead of the receiver's current time. This bounds the direct retry horizon to one day; applications needing longer shared retention can select the durable profile. Fresh request signatures and renewed delegations may recover the same still-valid message; its body and expiry do not change.

## 3. Acceptance transaction

After structural and cryptographic checks, the receiver MUST serialize the following against admission and delegation withdrawal:

1. Recheck the signature time window, clock, live recipient admission, delegation validity/revocation and message expiry.
2. Reject a previously used authenticated request nonce. Stage the fresh nonce reservation in this transaction without exceeding the replay-state budget. Commit it with acceptance, duplicate-result recovery or a permitted authenticated refusal; rollback must not leave partial custody.
3. Look up `(source, id)` in this receiver's acceptance ledger. The namespace is shared by all credentials for the actor at this receiver, not by a TLS connection or process.
4. If present and the exact HTTP body bytes differ, reject `conflict`. If present and equal, return the original receipt with `duplicate: true` after the current-authority checks; create no new handoff.
5. Otherwise atomically persist exact body, digest, minimal receipt, nonce and receiver custody before reporting acceptance.

An acceptance is ordered before or after a withdrawal at this receiver. Checking admission outside a transaction and committing under stale authority is nonconforming. Concurrent identical attempts with fresh nonces create exactly one handoff within the guaranteed horizon. Storage failure before commit MUST NOT report acceptance. If the result is lost after commit, retry recovers it without a second handoff.

The receiver MUST retain receipt/digest/deduplication state through the message expiry, even if its host has consumed the body. Live nonce state remains through the signature validity window. It MUST NOT evict live evidence to accept another request; it can reject `capacity`. Payload retention after local consumption is receiver policy. State may be reclaimed after its guarantee expires; this profile does not promise lifetime deduplication. Reusing `(source, id)` for a newly encoded intent, including a changed expiry after evidence was reclaimed, is a producer violation, and detection beyond the declared horizon is not promised.

After message expiry, a retry is `expired` even if a receipt still exists. A sender with a previously unknown outcome cannot infer that the message was never accepted. It must not automatically resend the application action under a new identity.

## 4. Receipt

The HTTP receipt is authenticated by the verified TLS endpoint. Its complete required fields are:

```json
{
  "coreVersion": "0.3",
  "profile": "direct/0.3",
  "outcome": "accepted",
  "delivery": "receiver-custody",
  "source": "urn:uuid:11111111-1111-4111-8111-111111111111",
  "id": "message-1",
  "to": "urn:uuid:22222222-2222-4222-8222-222222222222",
  "bodySha256": "64 lowercase hexadecimal characters",
  "acceptedAt": 1795147200,
  "expiresAt": 1795150800,
  "duplicate": false
}
```

Times are integer Unix seconds, not milliseconds. `bodySha256` hashes the exact request content bytes. A retry keeps every receipt field except `duplicate`. A client MUST verify the version/profile, identity, destination, digest, expiry, outcome, delivery label and duplicate/status relationship before treating a result as acceptance. The response is evidence observed directly from the receiver, not a nonrepudiable statement that can be verified by an unrelated third party.

## 5. Revocation

Recipient admission withdrawal is effective when committed at this receiver. An originating owner can send the authenticated delegation-withdrawal operation in the HTTP binding. That operation prevents later acceptance using that delegation at this receiver, including receipt disclosure through retry. Withdrawal does not remove previously accepted custody or recall a recipient's retained copy.

If an owner withdrawal has not reached a receiver, a valid delegation may continue to be accepted until it expires. The security profile limits delegation lifetime to 900 seconds and accepts no expiry grace. A failed or lost withdrawal response leaves propagation unknown until a successful retry. No global immediate withdrawal, root-key migration or automatic recovery from a compromised owner pin is implied.

Actor-key rotation uses a newly owner-signed delegation and withdrawal of old delegation identifiers. A currently valid replacement delegation for the same actor/owner/recipient can recover the receipt for an unchanged message. Revoking one delegation does not silently revoke all other delegations for that actor.

## 6. Compatibility

Direct delivery MUST NOT fabricate a conversation identifier or position. It MUST NOT satisfy a request for `durable-conversation/0.2` by returning a direct receipt. Conversely, the existing application may continue advertising its exact 0.2 profile without claiming this direct binding. A2A, Matrix and ActivityPub integrations require separately specified semantic mappings and conformance; none is advertised by this profile.
