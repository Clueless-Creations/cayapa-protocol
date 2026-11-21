# Host session lifecycle contract 1

Identifier: `host-session/1`. Status: selected host lifecycle contract; implementation and executed evidence are reported separately. Requirements use MUST, MUST NOT, SHOULD and MAY in the sense used by the [message core](../core/0.3.md).

This is an optional **host lifecycle conformance contract**, not a communication profile, transport binding, public enrollment API or new wire capability. It composes with existing [direct/0.3](../profiles/direct-0.3.md) actor identity and [owner delegation and actor signatures](../security/http-signatures-0.3.md). Current direct and durable wire contracts remain unchanged. A host does not add this identifier or session fields to existing advertisements or envelopes. It may name this contract and its exact evidence in implementation documentation and conformance reports.

## 1. Identity and scope

A **host session** is one logical unit of a host's agent activity that its owner elects to address separately. It may pause, resume and use several authenticated connections. The existing authenticated session, credential and durable connection semantics remain unchanged.

Each new separately addressable host session MUST receive a distinct actor URI. That actor URI is its canonical address. The accountable owner URI, actor URI and private native session association remain stable on legitimate resume. An endpoint is a separately approved route; titles, model names, processes, credentials and routes do not define the identity. A fork explicitly creates a different actor and address. An actor URI MUST NOT be reassigned to another host session, including after retirement.

The host allocates opaque, collision-resistant identifiers using established platform facilities. The fixture selects random UUID URNs; this does not constrain all conforming implementations to a new Cayapa identifier syntax. Identifiers remain subject to the selected communication binding. No identifier is dereferenced or published automatically.

This contract proves local lifecycle semantics and their effect on attributed exchange. It does not prove continuity of private reasoning, a unique physical installation, global exclusive execution or an external organization's implementation. The [portable fixture](../conformance/session-fixture.md) defines separately implementable observations.

## 2. Protected authority and durable binding

The host maintains one authoritative local binding journal for each controlled state domain. Its durable facts include:

| Fact | Required meaning |
| --- | --- |
| Native session reference | A private stable selector in this journal, bound to one logical host session. It is not a public address, credential or read grant. |
| Owner and actor | The accountable owner URI and stable actor URI. Their association cannot change silently. |
| Actor key and key identifier | The currently authorized actor public key and its identifier; private key custody remains protected separately. |
| Revision and lifecycle state | A positive monotonically increasing binding revision and active/retired state. Retirement is terminal in this contract. |
| Previously assigned identities and actor keys | Enough retained evidence to refuse reassignment or reuse within the journal, including after rotation or retirement. |
| Outgoing intents | Each staged message's actor-scoped identity and exact serialized bytes. Resume and rotation preserve this state; a fork does not copy it. |
| Mutation intents and outcomes | The stable request identity, immutable input and committed result needed to recover ambiguous new/fork/rotate/retire operations. |

The journal's serialization and durable commit boundary MUST cover current authorization, revision checks, uniqueness, finite capacities and mutation results. Concurrent operations MUST NOT allocate two results for one intent, overwrite a newer binding or reinstall an earlier state. Reads used for authorization and results observe the same authoritative state. A busy or failed store does not justify breaking a live lock or guessing success.

Implementations may use a database, files or native host storage. They MUST bound retained sessions, outgoing intents, mutation results and used-key evidence. Capacity refusal MUST preserve existing bindings, tombstones, exact intents and promised recovery. This revision defines no automatic eviction, deletion or identity-reuse operation. A limited implementation may refuse new work when full.

The journal and its configuration are part of the host's privileged custody boundary. Local access control must authorize the caller independently of incoming messages. Owner private signing material is supplied only to explicit owner administration; ordinary resume, staging and pending-intent reads MUST NOT receive it, issue delegations or gain owner administration. Private owner or actor keys MUST NOT be retained in reports or returned results.

The fixture verifies locally supplied key possession against configured public pins. This is a local test/control entrance, not a remote authentication protocol. Possession of an actor key does not authorize arbitrary remote content or the host's private memory. The host's trusted local consumer policy is a separate prerequisite for reading its staged outgoing bytes.

## 3. Explicit lifecycle operations

### New

An explicitly authorized new-session intent allocates a fresh actor URI and actor key association, starts revision 1 in active state, and durably binds the previously unused native session reference. Its result is committed before success is reported. A new request for an already bound reference conflicts; it never silently resumes or replaces that binding. A supplied actor key must differ from the owner key and every previously assigned actor key in the journal. New creates no delivery credential, admission, subscription, history grant or automatic network operation.

### Resume

Resume requires the existing session reference, expected current revision, current actor-key control and the host's current local authorization. It retains the same owner, actor, key association and outgoing intent namespace. It MUST NOT create a missing binding or infer continuity from a title, transcript, contact descriptor or route. A stale revision conflicts; unavailable or corrupt control state leaves continuity unknown; missing current key control refuses authorization. Retired bindings cannot resume.

Concurrent authorized resumes of the same binding refer to the same logical host session. They may establish separate authenticated connections with independent profile-defined progress. This contract does not require a globally exclusive session lease or turn scheduler.

Local identity continuity and delivery credentials have different lifetimes. A locally authorized resume can establish the retained identity even when a delivery delegation has expired. It grants no delivery in that state. A separately authorized replacement delegation may preserve the same actor and message namespace, subject to all existing recipient admission and withdrawal checks.

### Fork

Fork is explicit owner administration against the expected current revision of an active source binding. It allocates a new native reference, actor URI and actor key at revision 1. It does not alter the source binding. Owner administration is sufficient for this local operation; no source actor private key is required by the fixture.

A fork MUST NOT copy outgoing message intents, outcome uncertainty, delegated delivery authority, recipient admissions, receipts, connection progress, wake subscriptions or action permissions into the new actor. Any separately authorized copying of application context remains outside this communication contract. It cannot turn a previously uncertain action into a fresh automatic send.

### Rotate

Explicit owner administration may replace an active binding's actor key at its expected current revision. The actor URI, owner, native reference and outgoing intents remain unchanged, and the revision increases by one. The replacement key must be new to the journal and distinct from the owner key. Old key assignments remain reserved.

This local operation does not mint a delegation, withdraw any remote delegation or update recipient pins. Existing [actor-key rotation and receiver-local withdrawal](../profiles/direct-0.3.md#5-revocation) still govern network use. An old bounded delegation can remain usable remotely until its withdrawal commits or it expires. Owner-root transfer and automatic re-trust remain outside this contract.

### Retire

Explicit owner administration may retire an active binding at its expected revision. It increments the revision and retains the terminal binding, key-assignment history, mutation results and outgoing intents. It does not delete memory or recall content. Resume, fork-from-retired, new use of the same reference and new staging are refused. The explicitly authorized local pending-intent read remains available at the current revision and current actor key so retained uncertainty can be inspected.

Retirement is a local lifecycle fact, not global credential revocation, recipient admission withdrawal or evidence that a remote endpoint stopped accepting messages. Those controls remain separate.

## 4. Exact intents, idempotency and results

New, fork, rotate and retire use caller-retained mutation request identities. An authenticated identical retry recovers the original operation outcome without performing another mutation, even after later rotation or retirement. Its returned session snapshot MUST reflect the binding's **current** revision and state. Thus recovery of an earlier creation can return the original `created` outcome with `duplicate: true` and a currently retired session; it must not suggest the session became active again.

Authenticate current owner control and validate the input shape before disclosing a retained mutation outcome. For an exact recorded request, duplicate recovery precedes stale expected-revision, capacity and used-key checks that govern a new mutation. A changed immutable input under the same request identity conflicts. The [fixture](../conformance/session-fixture.md) selects exact raw input bytes as its retry equivalence; production serializers need not adopt that representation, but must define immutable intent equivalence unambiguously.

Prepare stages a structurally valid, bounded [Direct/0.3 body](../bindings/http-message-0.3.md#2-structured-cloudevent) whose actor and owner match the current active binding. It retains exact decoded bytes before reporting success, keyed by the message's existing `id` in that actor namespace. An authorized exact retry returns the existing prepared result; different bytes under that identity conflict. Nothing is sent and no delegation is issued. Initial structural validation may accept a past expiry; preparation is not proof of live delivery authority. Expiry does not permit renaming, rewriting or evicting the retained intent automatically.

Pending returns only that binding's staged outgoing messages to its explicitly authorized local consumer. It does not fetch a remote message, read a private transcript, acknowledge a receiver handoff or prove model consumption. Rotation and resume retain the exact bytes. Forking does not copy them. Staged bytes remain inert, including while a binding is retired.

Recognized refusals describe the current attempt only. Missing/corrupt authoritative state and storage uncertainty MUST NOT be converted to success, a fresh identity or a claim that a previous attempt never committed. Recovery uses the original intent. Implementations expose distinct successful, rejected and unknown outcomes through their chosen interface.

## 5. Existing cryptographic proof and permission boundaries

At delivery, the existing owner-signed delegation and actor HTTP signature prove owner, actor, key possession, intended recipient, scope and validity. The peer verifies its approved owner pin, current withdrawal and independent recipient admission under [http-signatures/0.3](../security/http-signatures-0.3.md). No new session certificate, token type, envelope attribute, sender-controlled key fetch or public enrollment operation is introduced.

New identity, valid delegation, trusted introduction, known address, resume and rotation grant no implicit recipient admission, session/history readership, wake or action authority. Receiver custody, authorized fetch, actual session read, wake, reply and execution remain separate observations. Same-owner actors receive no exception.

Native hosts may implement the contract directly. Authorized startup hooks and optional MCP/CLI bootstrap are implementation conveniences. Manual introduction and separately granted admission remain a complete supported path. DNS-to-HTTPS discovery is optional future work and cannot replace identity verification or admission. MCP Events remains an optional body-free admitted-message signal with current fetch authorization and independent host wake policy.

## 6. Copying, recovery and honest limits

A copied transcript, public descriptor, wrong native-reference association, missing key or partial record does not establish resume authority. A stale expected revision cannot overwrite a more recent authoritative journal. Configuration that disagrees with the retained owner control binding must not silently reparent or reset the journal.

If an attacker or administrator copies the **entire authoritative journal and every relevant controlling key**, this contract cannot cryptographically distinguish the copy from the original. It does not establish a unique physical host, clone prevention or global execution fencing. Similarly, a complete rollback of the authority store cannot be detected merely by revision numbers stored in that same rolled-back state. Restore procedures must preserve applicable withdrawal, intent and recovery guarantees; hardware-backed rollback resistance and cross-host controller transfer need separate contracts and evidence.

When the entire journal is absent, resume/fork/rotate/retire/prepare/pending report unknown continuity. Explicitly authorized `new` may initialize a fresh journal and new identity; it must not claim to recover a lost identity. A corrupt existing journal must never be overwritten as a fresh initialization. These results distinguish an acknowledged new start from a misleading successful resume.

## 7. Evidence and compatibility

Exercise the [portable session fixture](../conformance/session-fixture.md) against independently authored lifecycle implementations, then separately observe attributed exchange under the unchanged direct contract. Preserve the direct wire and durable compatibility gates. Report the lifecycle revision, implementation inputs, exact exercised cases, failure schedules and storage limits. The existing direct report does not retroactively prove this contract.

Local lifecycle conformance, independent external implementation, actual model-host consumption and production operation remain separate evidence. A CLI wrapper around an existing operator is not a second independent lifecycle implementation merely because it is installed separately. This contract changes neither existing actor identities nor durable connection/history semantics and requires no shared history or Cayapa-operated service.
