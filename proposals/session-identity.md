# Host session identity: next interoperability decision

## Superseded by the selected host lifecycle contract

The required outcomes below are now specified by [`host-session/1`](../extensions/host-session-1.md) and its [portable session fixture](../conformance/session-fixture.md). That selected mapping uses existing actor addresses and owner-delegation proof, with explicit local new/resume/fork/rotation/retirement behavior. It adds no communication profile, delivery field, public enrollment API or wire capability. Implementation and conformance evidence remain separate from specification selection.

The full original proposal follows as historical decision input. Its earlier unresolved representation and lifecycle questions are resolved only to the extent stated in the selected contract. Its evidence cautions, independent permission boundaries and remaining real-host/external/publication gates continue to apply. Complete control-state/key copying, rollback-resistant recovery and owner-root transfer are not newly proved guarantees.

## Original proposal

Status: proposal with owner-required outcomes; representation, versioning and lifecycle mechanisms remain open. This is not an implemented extension, a new capability advertisement or a change to core 0.3, direct/0.3 or durable-conversation/0.2. The acceptance cases below are planned, not passed results.

## Current contract and evidence

The [message core](../core/0.3.md) is settled: shared history, a Cayapa-operated service and official clients are unnecessary. [Direct/0.3](../profiles/direct-0.3.md) already separates actor identity, verified owner delegation and recipient-local admission. Its [security profile](../security/http-signatures-0.3.md) defines the current trust and proof mechanisms. The [durable-conversation/0.2 mapping](../profiles/durable-conversation-0.2.md) preserves existing identities, connection-scoped progress, history, receipts and retries.

The [direct report](../DIRECT-CONFORMANCE.md) records 193 passing Node/Python lab cases plus five separate resource checks. Those implementations were independently authored within this project. That evidence does not prove this proposed session lifecycle, an independent external implementation, actual model-host reads, wake or replies. The [durable report](../CONFORMANCE.md) retains its distinct historical single-operator proof.

The next decision is the smallest portable contract that lets another host distinguish a new separately addressable session from a resumed one and verify whose authority it uses. Native startup hooks and optional bootstrap tools implement that contract; they do not define it.

## Vocabulary and compatibility

| Term | Meaning in this proposal |
| --- | --- |
| Host session | A logical unit of a host's agent activity that its owner elects to address separately. It can pause, resume and use more than one authenticated connection. |
| Host session identity | The retained binding between that logical host session, its actor identifier/address and accountable owner. It is not the chat title, process identifier, model name, network route or credential. |
| New host session | A distinct logical activity selected by the host/owner as new, including a fork designated as independent. Copying an earlier transcript does not prove continuity. |
| Resume | Continuation of the same logical host session through its retained identity binding and currently valid authority. A lost binding cannot be replaced silently while claiming continuity. |
| Connection | An authenticated access instance. The existing durable contract's connection, and the repository glossary's authenticated Session, retain their current meaning. Reconnect or credential renewal alone is not a new host session. |

The proposed direct mapping reuses an existing actor URI as the canonical session address. An endpoint remains a separately selected route. This is a candidate mapping for the next decision, not permission to add a session field to the closed Direct/0.3 envelope. A new profile, extension or capability identifier must be selected explicitly if additional wire semantics are needed. Nothing here reassigns an existing actor, changes a durable connection ID or merges its receipt state with another connection.

## Required interoperable outcomes

These are requirements for the next selected contract. They do not claim that the current wire suite already verifies a host lifecycle.

| ID | Requirement | Observation that would establish it |
| --- | --- | --- |
| SI-1 | Distinct new host sessions receive distinct canonical addresses and actor bindings, including concurrent sessions under the same owner. Retired identities are never reassigned. | Two independently implemented hosts can distinguish the sessions without consulting a Cayapa service; a copied label, shared endpoint or common owner cannot collapse their attribution. |
| SI-2 | A legitimate resume retains the canonical identity/address and accountable-owner binding. Reconnect, restart or credential refresh cannot silently allocate a replacement or reset the message namespace. | A paused session resumes with the same identity, while retained uncertain sends and the profile's retry evidence continue to refer to the original actor and intent. |
| SI-3 | The peer can verify the owner-to-actor delegation under the selected trust/security profile, including actor-key possession, intended recipient, scope, lifetime and withdrawal. Names and payload assertions are insufficient. | A valid proof is accepted only against an independently approved trust basis; forged, substituted, expired, wrong-recipient and revoked authority is refused. No private owner key is given to a peer or to ordinary message interpretation. |
| SI-4 | Identity creation, introduction, resume and valid delegation grant no implicit permission to deliver, read a session/history, wake a host or act. Recipient-local admission remains independent and live at acceptance. | A correctly delegated session with no matching admission cannot deliver. A common owner or startup hook creates no exception. An address or custody receipt grants no session/history access, scheduling permission or tool authority. |
| SI-5 | Resume and authorized actor-key renewal preserve restrictions and current-authority checks. They cannot reinstall withdrawn admission, revive expired grants or recover a receipt under authority the selected profile now rejects. | Restart after withdrawal stays denied. A valid replacement delegation for the same actor retains the existing message namespace and does not widen its recipient or scope. |
| SI-6 | Manual introduction remains a complete supported path. Native incorporation and optional MCP/CLI bootstrap can establish the same verifiable binding without becoming protocol prerequisites. | Two implementations complete authorized introduction and exchange without a startup hook, DNS discovery, MCP, CLI, official SDK or Cayapa-operated service. |

The receiving party still decides admission. An owner may separately authorize scoped standing admission for linked agents; the effective grant, limits and withdrawal must be explicit. No per-message human prompt is required when a valid standing permission applies.

## Facts and permissions that stay separate

| Boundary | What it establishes | What it does not establish |
| --- | --- | --- |
| Owner delegation | A bounded claim that this actor may communicate on this owner's behalf, verified under the selected trust profile | Recipient admission, session readership, wake or action permission |
| Recipient admission | The recipient permits a particular sender and scope at the applicable acceptance boundary | Reading arbitrary session/history state or using the recipient's tools |
| Receiver custody | The selected profile's accepting authority committed its promised handoff or record | A session fetched it, a model read it, a host woke, or an action happened |
| Authorized fetch/session read | A permitted consumer retrieved content or a host separately observed its delivery to a particular session | Comprehension, a linked reply, another session's receipt or execution authority |
| Wake | A host was asked to schedule work, and actual scheduling is a separate observation | Admission, content access, read/receipt or a completed action |
| Action authority | The recipient host's independent permission to use tools or affect external systems | Authority inherited merely from delivered text, a receipt or a notification |

Direct/0.3 has no public session transcript API. Any local read, future remote-read interface or durable-history request needs its own current authorization. A model-read claim requires actual host evidence. A linked reply is a new authorized message, not an implication of custody or wake.

## Contract versus startup and bootstrap

The portable contract concerns identity, continuity, proofs and authority boundaries. It must be implementable from this bundle and referenced public standards. It must not require a particular host event, plugin, file layout, vendor account, enrollment command or official package.

| Implementation path | Responsibility | Boundary |
| --- | --- | --- |
| Native host | Establish and retain the owner-authorized session binding in its own lifecycle and custody controls | Native support needs no MCP, CLI or resident Cayapa package. |
| Authorized startup hook | Invoke the host's chosen enrollment/resume procedure when its policy permits | Hook execution does not choose admission, readers, wake permission or external actions. |
| Optional MCP/CLI bootstrap | Expose the same bounded owner/host controls where native support is absent | Tool installation and invocation alone prove no grant; advertise only the selected supported profile. |
| Manual introduction | Exchange approved identity, owner proof and route information through an authorized channel, then establish any separate admission | This remains usable when all automatic discovery and startup integration are absent. Introduction is not admission. |

A resume request must refer to the retained owner-authorized binding. A title, browser tab, copied transcript or endpoint response alone cannot substitute for continuity and current key control. If the binding is missing, conflicting or untrusted, report that continuity is unestablished. Explicitly creating a new identity is possible, but it must be reported as a new host session rather than a successful resume. The exact portable representation of continuity evidence remains a decision below.

Existing actor-key rotation may preserve an identity under current owner authority. Automatic owner-root replacement, controller transfer, cross-device recovery and unattended renewal require their own selected contracts; this proposal does not implement them or weaken current withdrawal semantics.

## Optional discovery and wake adapters

**DNS-to-HTTPS discovery is future work, not a Direct/0.3 or session-identity acceptance dependency.** It may eventually supply candidate routes or capability locations. It cannot establish owner identity, replace approved trust pins, grant admission or wake permission, or carry the message in place of the normal authenticated exchange. A future proposal must address spoofing, redirects/cross-origin changes, downgrade, stale records, correlation and disclosure of private session addresses. A DNS result, even an authenticated one, cannot substitute for owner-delegation verification or recipient admission. Manually approved routes and trust remain valid.

**MCP Events is an optional adapter.** A qualifying event signals an already admitted message using only minimal, authorized reference metadata. It carries no message body or body excerpt. The consumer obtains content through the selected profile's normal authorized fetch or local handoff; it rechecks current access, including revocation since the event was created. Event visibility and subscription scope need their own authorization. Duplicate, delayed or stale signals cannot revive admission or cause duplicate application effects by themselves.

The host's wake policy still decides whether to schedule a turn. Event transport acceptance, actual wake, authorized fetch, session read, acknowledgment and reply require separate observations. Native hosts may connect their authorized handoff directly to their own scheduler and need no MCP. This proposal selects neither a new MCP event name/schema nor a vendor-specific delivery mode, and makes no claim that a particular client supports it.

## Open decisions before a normative session contract

1. **Representation and versioning:** can existing actor identity and owner delegation express the complete portable guarantee, or is a separately advertised lifecycle extension needed? Select any canonical public binding, claims and test interface without changing existing closed envelopes implicitly.
2. **New, resume and fork boundaries:** specify how a host exposes its lifecycle decision to an independent implementation and what continuity proof it can validate. Define concurrent resumes, stale snapshots, missing binding and explicit retirement without reassigning identities.
3. **Custody and continuity:** select the minimum retained state and current-control proof; specify key replacement, unavailable authority and conflicting bindings. Keep any owner-root recovery or transfer outside the supported claim until separately specified and tested.
4. **Privacy and disclosure:** define which identity/address metadata is shareable, through whose permission, and how to avoid automatic directory publication or cross-session disclosure.
5. **Conformance boundary:** define portable fabricated fixture controls and observable results for the cases below without importing host internals or requiring an official bootstrap tool.

DNS discovery, vendor startup implementation, MCP Events qualification and standalone publication each have separate completion gates. None is needed to retain the existing manually introduced Direct/0.3 path.

## Planned acceptance matrix

All rows are **unexecuted for the proposed session contract**. Existing direct negative/recovery cases remain useful baseline evidence, not substitutes for these lifecycle observations.

| Case | Required result |
| --- | --- |
| New sessions under one owner, including simultaneous creation | Distinct identities/addresses and independently verifiable bindings; no cross-session receipt or authority inheritance |
| Pause/resume, host restart and reconnect | Same retained session identity; independent authenticated connections keep their own profile-defined progress |
| Fork, missing binding, copied state or conflicting resume | Honest new-session or unresolved-continuity outcome; no silent identity theft, reassignment or permission restoration |
| Renew/rotate an actor key | Same identity and message namespace only under valid owner authority; no implicit owner-root transfer or wider admission |
| Valid delegation without recipient admission | Delivery refused, including same-owner actors and a successful startup/bootstrap invocation |
| Forged owner proof, substituted actor/route, wrong destination or expired/revoked authority | Refusal without custody or unauthorized outcome disclosure |
| Restart/resume after withdrawal, including a delayed message or event | Current authority wins; no reinstated admission, read access or wake permission |
| Lost delivery result followed by resume and exact retry | Preserve original intent and uncertainty; recover only what current authority and the chosen profile permit |
| Custody with no session consumer or scheduler | Report custody only; no inferred session read, wake, reply or execution |
| Manual and native paths without adapters or discovery | Equivalent identity/authority semantics and successful authorized exchange |

Reports must name exact contract versions, implementation sources and authoring inputs, identities, trust bootstrap, storage boundaries and network topology. Report lab conformance, an independent external implementation and actual host consumption as separate evidence. Publication of this proposal or completion of a checklist is none of those observations.
