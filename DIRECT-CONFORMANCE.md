# Direct/0.3: independently implemented exchange and recovery

Reviewed November 19, 2026, Chicago. The final recorded exchange completed at `2026-11-20T05:58:40Z`.

**Result: 193 passed, 0 failed, 0 skipped.** Two independently authored implementations exchanged messages in both directions over verified HTTPS with separate owner keys, actor keys, TLS keys and persistence. The [case-level report](evidence/direct-conformance.json) records 96 cases in each direction plus the published signature-vector group. The separate [resource report](evidence/direct-resources.json) records **5 passed, 0 failed, 0 skipped**.

This is executed interoperability evidence for **core 0.3 / direct/0.3 / http-message/0.3 / http-signatures/0.3**. The test ran on one Linux machine using isolated processes and loopback HTTPS. It establishes the named implementations and schedules below, not public deployment, another protocol's conformance, arbitrary external implementations, model consumption or application execution. The [durable-conversation/0.2 result](CONFORMANCE.md) is a separate compatibility claim.

## Independent implementation and execution boundary

| Participant | Implementation and observed runtime | Persistence |
| --- | --- | --- |
| Left endpoint and native sender | Node `v24.22.3`, standard runtime networking and cryptography, no external packages | Independently written bounded JSON journal; temporary-file write, file synchronization, atomic rename and directory synchronization |
| Right endpoint and native sender | Python `3.12.14`, standard HTTP/TLS facilities and `cryptography 50.0.0` | Independently written SQLite transactions with persisted custody, replay, admission and withdrawal state |
| Public test coordinator | Python `3.12.14`, `cryptography 50.0.0`; Python TLS reports `OpenSSL 3.5.8 25 Aug 2026` | Private disposable fixture files and content-free result reports |

The two operator authors worked in isolated agent sessions within this project. Each received the same frozen published core, profile, binding, security, schema, signature vectors and fixture-adapter contract, plus repository engineering instructions. Neither author read the other's operator, the existing application/client or the new conformance runner. Their source and provenance records live outside this standalone bundle. This is independent authoring within one coordinated project, not third-party certification.

The coordinator was separately written from the published contract. Positive exchanges invoke each implementation's native sender against the other's receiver. Negative probes additionally use a third, independently written HTTP signing path in the public suite. It imports neither operator, their stores nor an official Cayapa SDK. Local recipient custody is inspected only through the published fixture adapter.

Before the final run, the entire protocol directory and each operator directory were copied into separate locations outside the checkout. The runner executed from that copied specification, with both native commands pointing to the separately copied implementations. It checks that its recorded source inputs and implementation entry files remain unchanged throughout the exchange. The recorded hashes were also compared with the release checkout before this report was included.

| Tested source | SHA-256 |
| --- | --- |
| Node `operator.mjs` | `47d458bd11a9a77050759ae3a198750713f920036c6e8185d7aeb9bad4363447` |
| Python `operator.py` | `0cc1e3384d0c885d9dd6b1e894b87c24268c58528455950cbc9a6ef249b1dcdb` |

The [case report](evidence/direct-conformance.json) contains the full contract, schema, vector and runner hashes. Its fixture uses independently generated owner and actor key pairs, not a common identity issuer. The disposable CA signs only localhost endpoint certificates. Receivers receive owner public-key pins and their own TLS key; sender/control processes receive only the explicitly selected private signing-key file. This is logical key separation in test processes, not a claim of operating-system isolation between different administrators on one machine.

## What actually passed

| Contract boundary | Executed observations in both directions |
| --- | --- |
| Native exchange and custody | Binary, UTF-8, empty and unfamiliar media-type payloads preserved in exact accepted envelope bytes; complete receipts bind actor, owner-established authority, recipient, body digest and expiry. No conversation or shared transcript was provisioned. |
| Declared bounds | Maximum payload and envelope accepted; over-limit payload/body and oversized headers refused. Saturated live message, nonce and control state refused new work without evicting promised evidence. |
| Idempotency and concurrency | Fresh processes and fresh nonces recovered original acceptance; changed bytes, including changed serialization whitespace, conflicted. Concurrent identical intents created one handoff. |
| Replay | Reused actor and owner nonces failed, including across replacement delegations, control routes and restart. An invalid signature could not reserve a valid actor's chosen nonce. |
| Authentication and attribution | Forged owner/actor signatures, unknown pins, wrong destination/source/owner, altered body/digest/target, missing signature coverage and wrong signature domain failed. |
| Delegation restrictions | Wrong scope/audience, expired or future authority, excessive lifetimes, JWT algorithm confusion, duplicate members, fractional integer-token syntax and embedded private key material failed. Actor keys matching the issuer or another pinned owner key failed even under different key identifiers. |
| Recipient consent | A correctly owner-authorized identity without matching recipient admission failed. An actor could not issue owner withdrawal; a foreign owner could not withdraw the recipient owner's admission. |
| Representation | Unsupported profiles/media types, extra envelope controls, duplicate JSON fields, invalid UTF-8, byte-order marks, lone surrogates, malformed URI/media values and noncanonical base64 failed. Duplicate protected headers and unsupported transfer/content encodings were refused. |
| Originating-owner withdrawal | Signed delegation withdrawal was acknowledged and remained effective after restart. Fresh sends and prior-receipt recovery under withdrawn authority failed. Preemptive withdrawal of an unseen delegation also survived restart. |
| Recipient-owner withdrawal | Acknowledged admission withdrawal remained effective after restart; startup did not reinstall the initial grant. Exact retries under the withdrawn grant could not retrieve an old acceptance receipt. |
| Actor-key rotation | A new owner-signed delegation for the same admitted actor, with a different actor key, sent new messages and recovered an unchanged prior intent. This is actor-key replacement, not owner-root transfer. |
| In-flight boundaries | A signed partial upload completed only after owner withdrawal committed and was refused. A signature that expired while the body was held also failed. These are concrete schedules, not exhaustive concurrency verification. |
| Interrupted delivery | A half-sent body followed by forced receiver termination produced no acceptance; restart and complete retry created exactly one handoff. |
| Acceptance response loss | The receiver committed, consumed the local test fault, and closed without a response. The native sender reported unknown. The harness forcibly terminated the receiver with SIGKILL; restart plus fresh authenticated retry returned the original duplicate result and one local handoff. |
| Withdrawal response loss | The receiver committed withdrawal and dropped its response. The sender reported unknown. After SIGKILL and restart, the same control intent recovered the committed result; withdrawn authority remained unusable. |
| Pending remote withdrawal | Withdrawal sent while the receiver was stopped remained unknown. On restart, still-valid authority could be used until the receiver received and committed the withdrawal. Later use failed. The suite deliberately verifies this limited boundary rather than claiming global immediate revocation. |
| Misleading native responses | Wrong TLS hostname, an untrusted CA, redirects, oversized/malformed responses, wrong receipt digest or recipient, status/duplicate mismatch, fractional acceptance time, mismatched withdrawal request ID and an unrecognized problem document all remained unknown. |

The deterministic response-loss hook is local test instrumentation enabled only with explicit test mode. A network request cannot enable it. SIGKILL tests process-loss recovery after a committed operation; they do not simulate storage-device power loss or every filesystem failure. Both implementations depend on the durability properties of their selected local storage environment.

## Review findings and corrections

The first 161-case exchange passed, but release review continued against concrete remaining risks. Independent review identified an ambiguity in the phrase “owner and actor keys are distinct.” The public security contract now requires checking actor key bytes against every current locally pinned owner key. Both authors received that same published clarification; Python was updated independently and public cases now exercise issuer-key and other-owner-key reuse.

Additional tests exercised forged withdrawal acknowledgements, unauthenticated nonce reservation, cross-route controls, replacement delegations, expiry and forced termination. A separate bounded probe found that the original test adapter capture cleaned up only its immediate process, leaving a wrapper's descendant running. The direct harness now creates POSIX process groups and terminates the group on success, failure and timeout, reaping its direct children. It documents the foreground/non-detaching fixture requirement and the operating-system scope of this test orchestration.

The five resource regressions exercise successful-wrapper descendants, finite oversized output, a stalled adapter that ignores SIGTERM, normal server shutdown and invalid readiness. Their observations and tested runner hash are [published separately](evidence/direct-resources.json). This correction changes the public testing facility, not the wire protocol or the two operators' message semantics.

## Reproduce from the specification alone

Requirements for this public runner are **POSIX, Python 3.11+ and the declared cryptography dependency**. An implementation may use another operating system or language. It only needs an adapter for the [public fixture contract](conformance/direct-fixture.md), with its own runtime dependencies installed. No official Cayapa package is required.

From a copied protocol directory:

```sh
python3 -m pip install -r conformance/requirements.txt
python3 check.py
python3 conformance/check-direct-resources.py
python3 conformance/run_direct.py \
  --left-command-json '["node","/absolute/path/to/operator.mjs"]' \
  --right-command-json '["python3","/absolute/path/to/operator.py"]' \
  --work-dir /tmp/cayapa-new-private-fixture \
  --report /tmp/cayapa-direct-report.json
```

Supply a new or empty private work directory. The program generates test identity/certificate material there; do not publish that directory. Publish only the content-free report. The [native adoption guide](IMPLEMENTING.md) explains how a model host or framework can embed the same sending, admission, receiving and local-consumer responsibilities without exposing this fixture CLI to its users.

The repository's CI wrapper separately copies the bundle and each supplied operator before running these checks. CI uses Node 22 and Python 3.12; its live artifacts identify its tested revision and actual runtime. Release success requires the direct job and the separate durable-profile compatibility job. A checked-in historical report alone does not replace those gates.

## Claim limits and remaining adoption work

The evidence establishes the tested independent direct combination. It does not establish internet-wide discovery, automated owner-root recovery or transfer, public-name verification, shared-history federation, mailbox profiles, standards bridges, end-to-end encryption, transferable signed receipts, payments, marketplace semantics, exactly-once application effects or malicious-operator resistance.

The owner pins and recipient admissions are explicit local provisioning. Optional local tooling now supplies explicit peer introduction, owner-issued credentials, an outgoing intent store and bounded receiving/acknowledgment in the Python implementation. Its installed-package proof is separate from this wire suite; actual model-host key custody and scheduling still need observation. Local endpoint custody is not evidence that an LLM read the message or that a host scheduled a turn. An actual two-agent installation needs the intended hosts, approved endpoints and standing grants, followed by an observed end-to-end host handoff. The protocol does not require those hosts to adopt these reference implementations.

The Python implementation now retains a pending local handoff until explicit local acknowledgment, with a separate bounded queue and acknowledgment ledger. The wire retry horizon remains unchanged. The maintained implementation passed this complete suite again; original independent-authoring provenance remains distinct from later implementation maintenance.

The existing Cayapa application continues on the preserved durable profile. Its separately documented collection/page-budget gaps remain open. The optional [same-owner creation extension](extensions/agent-creation-1.md) implements explicit owner readership with its [own conformance evidence](CREATION-CONFORMANCE.md). This direct proof neither exercises that conversation-creation operation nor silently grants owner readership.
