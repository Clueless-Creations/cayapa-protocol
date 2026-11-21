# Implementing Cayapa and adding native support

An independent developer can implement Cayapa from this directory and its referenced public standards. A model developer or agent framework can embed the same contract in its runtime. There is no mandatory Cayapa SDK, registry, hosted service, MCP integration or CLI. The endpoint **operator** is a role your host can implement itself.

Start with the [core](core/0.3.md), select a complete [profile](#choose-the-responsibility-you-need), then implement that profile's binding and security requirements. This guide explains the adoption workflow; exact validation, wire representation and acceptance rules live in the linked contracts.

## Current baseline and selected session lifecycle

Existing direct and durable contracts remain the delivery baseline. The selected [host-session/1 contract](extensions/host-session-1.md) gives separately addressable logical host sessions distinct actor URIs and stable owner/actor identity on resume. Its [portable fixture](conformance/session-fixture.md) specifies new, fork, rotate, retire, resume and exact outgoing-intent observations; [session conformance](SESSION-CONFORMANCE.md) records lifecycle evidence separately from the unchanged direct wire suite. It is a host lifecycle contract, not a new communication profile or advertised wire capability. The [original proposal](proposals/session-identity.md) remains as history.

The contract distinguishes a logical host session from an authenticated connection. Retain the protected native-reference binding, current actor-key association, revision, terminal identities and exact pending intents across restarts. Local resume uses current host/actor authorization and does not require an unexpired delivery token; every subsequent send still requires current owner delegation and separate recipient admission. Rotation preserves the actor and intent namespace, while local retirement does not revoke remote authority. Full copies of controlling state and keys cannot be distinguished, and a completely rolled-back journal cannot prove its own freshness.

Native startup, authorized hooks and optional MCP/CLI bootstrap are host implementation choices; none grants delivery, session/history readership, wake or action permission. The fixture's process controls are optional test integration, not a mandatory end-user CLI. Keep the manual introduction path in [trust and consent](#establish-trust-and-consent-before-sending) working without those integrations. DNS-to-HTTPS discovery remains optional future work and cannot replace identity verification or admission.

An optional MCP Events adapter may signal an already admitted message using minimal authorized reference metadata without its body. Obtain content through normal authorized fetch or local handoff, recheck access after revocation and follow independent host wake policy. A native host can use its own receiving/scheduling path with no MCP. This is an adapter boundary, not a new wire operation or a claim of support in any vendor host.

Report the [lab conformance](DIRECT-CONFORMANCE.md), an independent external implementation and actual host consumption as separate evidence. The specification, this guide and the suite form the standalone publication track; shipping a connector, SDK or hosted endpoint is not a prerequisite or a substitute for that release.

## Choose the responsibility you need

| Requirement | Contract | What the host takes on |
| --- | --- | --- |
| Deliver opaque content directly to a consenting agent with recoverable custody | [Direct/0.3](profiles/direct-0.3.md), [HTTP message/0.3](bindings/http-message-0.3.md), [HTTP signatures/0.3](security/http-signatures-0.3.md) | Authenticated HTTPS endpoint, live recipient admission, atomic private receiving handoff and retained retry evidence |
| Participate in an existing shared ordered conversation | [Durable-conversation/0.2](profiles/durable-conversation-0.2.md), [0.2 specification](specification.md), [HTTP](bindings/http.md) or [MCP](bindings/mcp.md) | Existing actor credential, accepted membership, history/continuation/receipt semantics of that profile |
| Add tasks, subscriptions, services, payments or a visual workspace | The selected communication contract plus an application agreement | Application meaning and execution permissions, with no implicit widening of communication authority |

The first direct profile has a durable recipient handoff, but no shared conversation or public transcript. A future transient or mailbox profile may choose a different responsibility. Do not claim such a profile until its contract exists and its compatibility is explicit.

## Three native adoption paths

| Adopter | Integration point | Local responsibilities |
| --- | --- | --- |
| **Model developer or hosted agent runtime** | Built-in send operation and receiving endpoint, backed by the host's identity and policy controls | Keep owner approval and key custody outside model-controlled message content; expose honest outcomes; route the private handoff into a scheduled turn only under host policy |
| **Open-source agent framework** | Communication port with adapters for the supported profile combinations | Preserve exact outgoing intent, separate recipient input from administrative instructions, expose receiving lifecycle and outcome evidence independently of tools or conversation UI |
| **Independent agent developer** | A small endpoint and native sender written with standard libraries, either embedded or separately authorized | Manage endpoint availability, local grants, private keys, persistent acceptance state, bounded retries and recovery |

A command-line wrapper can help a computer-using agent invoke a sender. MCP can expose compatible operations through a host's existing integration facilities. A library can reduce implementation effort. Each is optional packaging, and each must declare which profile it actually supports. The existing 0.2 client or MCP binding is not automatically a 0.3 implementation.

The optional Python direct-host implementation used in the lab supplies explicit owner setup, a local address book, bounded delegations, durable outgoing intents and bounded receiving. Its package and local commands are implementation choices outside this bundle. Native adopters may use their own controls and storage; no part of this specification requires that package. Its installation evidence is distinct from actual model-host scheduling.

## A direct implementation's components

The [fixture contract](conformance/direct-fixture.md) is a useful test boundary, not a mandatory runtime architecture. In a real host, the same responsibilities can live in one process:

| Component | Required responsibility |
| --- | --- |
| Trust and owner controls | Maintain authorized owner public-key pins, recipient admissions and persistent withdrawal state; keep private owner/actor keys separate |
| Native sender and outbox | Retain each stable intent and its exact serialized bytes, sign each attempt, verify the peer's TLS identity and validate the complete outcome |
| Receiving endpoint | Verify the selected representation, owner delegation, actor signature, destination, current admission, validity and replay constraints |
| Acceptance transaction | Serialize current authority with duplicate/conflict handling; atomically persist the handoff, original receipt and required live evidence |
| Local consumer | Read the recipient's private handoff and apply the host's own retention, scheduling and execution policy |

Choose storage that can meet the profile's atomicity, restart and retention rules. A database product is not mandated. An in-memory cache alone cannot satisfy direct receiver custody. A durable queue may carry the payload, but the acceptance, deduplication and current-authority decision still require the published consistency boundary.

## Establish trust and consent before sending

1. **Approve the peer and endpoint.** Configure the intended recipient actor and its HTTPS origin. Verify the certificate and hostname; do not follow signed-request redirects. Endpoint identity is distinct from the actor's owner identity.
2. **Introduce owner keys through an authorized channel.** Each receiver pins the approved owner identifier, key identifier and public key. Pins establish local trust; they do not prove a public name, and the protocol does not fetch keys from message-controlled URLs.
3. **Grant sender authority.** The sender's owner issues a bounded delegation for that actor key, intended recipient and delivery scope. The actor proves possession of its own key. The receiver does not need the sender's private owner or actor keys.
4. **Grant recipient admission independently.** The recipient's owner authorizes the intended sender owner/actor, recipient and scope for a validity interval. A sender's valid delegation cannot create this consent.
5. **Read capabilities through the approved origin.** Check the exact core, profile, binding, security and limits. Refuse to assume support from a product name or software package version.

The required pin, delegation and admission forms are specified by the [security profile](security/http-signatures-0.3.md). Private deployment may supply these through existing owner controls; no global Cayapa issuer or public directory is needed. Key introduction and consent remain explicit even when both agents are owned by one person.

## Send, accept and hand off

The selected [HTTP binding](bindings/http-message-0.3.md) reuses a constrained CloudEvents structured envelope. Use the schema and vectors as aids, and follow the normative prose for rules a schema cannot enforce. There is no custom JSON canonicalization step.

1. Create a new actor-scoped message identifier, intended recipient, immutable expiry, media type and opaque payload. Serialize the complete envelope once and retain its exact bytes in the sender's outbox before sending.
2. Compute the standard body digest and sign the attempt under the selected HTTP Message Signatures profile with a fresh nonce. Use a live owner-signed delegation. The request signature protects the exact body and intended HTTP target.
3. At the receiver, validate representation and limits, then authenticate the owner/actor binding, recipient, live admission, delegation and attempt. Before commit, recheck current authority and time within the acceptance serialization boundary.
4. Commit the recipient's durable handoff and acceptance evidence atomically, or refuse without a new acceptance. An identical authorized retry returns the original receipt; a changed body under the same intent conflicts.
5. At the sender, validate status and the complete receipt against the original intent and body digest. A bare success status is insufficient. Retain uncertainty if the response cannot establish the specified outcome.
6. Let the recipient's local consumer read the handoff. Starting a model turn, showing a message in a screen, executing a tool and acknowledging an application outcome are separate host decisions.

Direct acceptance means `receiver-custody`. It does not mean a model has read the message. If an application needs proof of processing or an answer, define and send a separate application-level response under the same authority rules. A protocol receipt is not that response.

## Lifetimes, retries and uncertain outcomes

The first direct profile bounds messages, delegations and signed attempts independently. Current limits and clock rules are normative in the [direct](profiles/direct-0.3.md), [HTTP](bindings/http-message-0.3.md) and [security](security/http-signatures-0.3.md) documents. Do not copy a signature's expiry into a message's immutable lifetime or assume that renewing authority renews the message.

| Observation | Host behavior |
| --- | --- |
| Valid accepted receipt | Record the receiver's custody fact. Do not infer model execution. |
| Recognized refusal | Record that this attempt created no new acceptance. Preserve any uncertainty from an earlier attempt. |
| Timeout, TLS failure, connection loss, malformed or mismatching success | Report unknown. Retain the intent so the caller can recover it. |
| Retry of a still-valid intent | Send the identical retained body with fresh attempt authentication and current authority. |
| Changed body, recipient, profile or expiry under the same message identity | Treat as a conflicting intent; do not silently rewrite the earlier message. |
| Message lifetime has ended | Stop presenting new attempts as a recovery path. Expiry does not establish that an earlier attempt was never accepted. |

Apply finite deadlines, response caps and bounded retry policy. The conformance fixture's native sender has specific bounds for reproducibility; production scheduling belongs to the host. The protocol does not force continuous polling or start another model turn.

The receiver retains minimal duplicate/acceptance evidence through the message's validity horizon even if the payload has been consumed. Live evidence cannot be evicted just to accept more messages. Refuse capacity when necessary. Restart must reopen the same state without replaying initial grants over recorded withdrawals.

## Withdraw authority and recover safely

Recipient admission withdrawal is effective at the receiver's committed authority boundary. An originating owner can also send the standardized signed delegation-withdrawal request to that receiver. Test both controls through their actual authenticated endpoints.

Fresh attempts and duplicate-receipt recovery under revoked authority must fail. A partially received request cannot rely on an earlier authority check after withdrawal has committed. The profile requires this serialization; it does not require a specific locking or database design.

A lost withdrawal response is unknown. Retry the same control intent with a fresh signature to recover its committed result. If a remote receiver has not received the withdrawal, that receiver's existing bounded delegation may remain usable until expiry. Describe this as receiver-local withdrawal with a bounded remote exposure horizon, never global immediate revocation. Already accepted custody is not recalled.

The direct contract supports a new owner-authorized actor key for the same admitted identity; duplicate detection remains keyed by message identity, not by the new credential. Owner-root replacement requires an authorized local retrust process in this version. Automatic recovery, transfer and globally synchronized key retirement remain separate work.

## Keep application meaning outside the core

For a host choosing the durable profile, optional [agent-creation version 1](extensions/agent-creation-1.md) removes the need to prepare every same-owner conversation manually. Check both `agentCreation` and bounded collection capabilities, inspect the actor's current grant, resolve stable active target IDs through `creation_targets`, and use one retained creation intent at that exact policy revision. The grant chooses owner readership explicitly. Creation establishes a conversation and initial memberships; it does not deliver a message or start a recipient model. Existing room access is independent of later grant withdrawal. The [portable creation fixture and runner](conformance/creation-fixture.md) define how to verify this addition without any reference implementation import.

A host can receive a service request, a subscribed event or another agent's answer without creating a conversation screen. Media type and payload belong to the application agreement. Communication authority permits only the specified communication; it grants no filesystem access, payment approval or tool execution.

Treat all incoming content as untrusted data. Keep host controls, owner credentials and security policy outside the payload interpretation path. Rendering and remote fetching require the host's own explicit policy. An owner's ability to administer an agent does not silently add that owner as a human reader.

## Prove your implementation independently

Implement from the published contracts, schemas and vectors. Run each native sender against a different implementation's receiver, using independently generated owner/actor keys and separate persistence. Avoid importing another implementation's codec, verifier or store merely to make the test pass. Standard cryptographic and networking libraries are appropriate.

The portable [fixture contract](conformance/direct-fixture.md) specifies process lifecycle, native send/control invocation and a local recipient-handoff observation. Its local inspection is not a public history API. Its deterministic response-loss hook exists only in explicit test mode. An adapter can translate those controls into your host's own test infrastructure without requiring that production users install a CLI.

The standalone harness uses Python 3.11+, POSIX process groups for fixture cleanup, and the pinned `cryptography` dependency in [requirements.txt](conformance/requirements.txt). This test-orchestration requirement does not restrict the protocol to a host operating system. For example, from a copied bundle:

```sh
python3 -m venv /tmp/cayapa-conformance-venv
/tmp/cayapa-conformance-venv/bin/pip install -r conformance/requirements.txt
/tmp/cayapa-conformance-venv/bin/python conformance/run_direct.py \
  --left-command-json '["node","/absolute/path/to/left-operator.mjs"]' \
  --right-command-json '["python3","/absolute/path/to/right-operator.py"]' \
  --work-dir /tmp/cayapa-fresh-private-fixture \
  --report /tmp/cayapa-direct-report.json
```

Use a new, empty private work directory and supply independently implemented fixture adapters. The command paths above are examples, not required Cayapa packages. Each implementation's own runtime dependencies remain its responsibility. The bundle's `check.py` verifies distribution integrity separately from this behavioral exchange.

Required evidence includes both directions over verified HTTPS, opaque byte preservation, honest outcomes, exact retries, changed-intent conflicts, replay and identity/admission refusals, withdrawal, key rotation and restart after response loss. Preserve failures and skips. One successful exchange does not replace negative or recovery cases. The [direct report](DIRECT-CONFORMANCE.md) states which cases the lab implementations actually passed and the limits of that result.

Local fabricated participants establish only the exercised protocol behavior. Before claiming a successful real-host integration, separately observe installation, approved identity/consent, receiving handoff and the host's actual scheduling behavior. Public operation and production security require operational evidence beyond the local conformance suite.

## Preserve existing 0.2 applications

An existing durable-conversation implementation remains conforming by preserving its [0.2 contract](specification.md) and passing its [separate conformance suite](conformance/README.md). Do not rewrite stored records, change retry digests, broaden owner readership or replace durable receipts with direct custody receipts as part of adopting the new architecture.

A 0.2-only application need not advertise 0.3. An application that later adds direct delivery should advertise both combinations accurately and keep their identities, retry rules, receipts and capability discovery explicit. A bridge is a new authority and delivery boundary requiring its own specification; it must not silently convert a direct message into a shared conversation with a wider audience.
