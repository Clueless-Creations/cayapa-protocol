import argparse
import datetime
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from run import CheckFailure, ConfigurationFailure, Suite, encoded, require, safe_endpoint


ROLES = {"owner", "foreign_owner", "creator", "creator2", "peer", "spare", "outsider"}


class CreationSuite(Suite):
    def preflight_creation(self):
        advertised = self.wire.request("/capabilities", method="GET")["body"]
        capability = advertised.get("capabilities", {}).get("agentCreation", {})
        require(advertised.get("protocolVersion") == "0.2" and capability == {
            "version": "1", "maxTargets": 9, "maxGrantDays": 90, "maxConversations": 100,
            "ownerReadership": ["reader_from_creation", "excluded"], "mutationReceiptTtlMs": 604800000, "maxMutationEvidence": 4096,
        }, "Creation extension capability differs")
        require("creation_targets" in advertised.get("capabilities", {}).get("collectionPage", {}).get("collections", []), "Creation discovery is not advertised")
        for role in ROLES:
            self.identities[role] = self.ok(self.http, role, "whoami")
        require(self.identities["owner"]["actor"]["kind"] == "person" and self.identities["foreign_owner"]["actor"]["kind"] == "person", "Owner fixture roles must be person actors")
        require(self.identities["owner"]["owner"]["id"] != self.identities["foreign_owner"]["owner"]["id"], "Fixture needs two independent owner identities")
        for role in ("creator", "creator2", "peer", "spare"):
            require(self.identities[role]["actor"]["kind"] == "agent" and self.identities[role]["owner"]["id"] == self.identities["owner"]["owner"]["id"], "Creation participant does not belong to the intended owner")
        require(self.identities["outsider"]["owner"]["id"] == self.identities["foreign_owner"]["owner"]["id"], "Outsider is not independently owned")
        require(self.identities["creator"]["actor"]["id"] == self.identities["creator2"]["actor"]["id"]
                and self.identities["creator"]["connectionId"] != self.identities["creator2"]["connectionId"], "Creator needs two independent credentials")
        require(len({self.actor(role) for role in ("creator", "peer", "spare", "outsider")}) == 4, "Fixture actors must be distinct")
        self.mcp.rpc(self.tokens["creator"], "initialize", {"protocolVersion": "2025-11-25", "clientInfo": {"name": "creation-conformance", "version": "1"}})
        tools = self.mcp.rpc(self.tokens["creator"], "tools/list")["result"]["tools"]
        require({"get_creation_grant", "set_creation_grant", "revoke_creation_grant", "create_agent_conversation"} <= {tool["name"] for tool in tools}, "MCP omits a declared creation operation")
        return {"separateOwners": True, "replaceableCreatorCredentials": True, "bindings": ["http", "mcp"]}

    def actor(self, role):
        return self.identities[role]["actor"]["id"]

    def grant_input(self, role, revision, readership, budget=2):
        return {"actor": self.actor(role), "expectedRevision": revision, "ownerReadership": readership,
                "expiresAt": int(time.time() * 1000) + 3600000, "maxConversations": budget, "intentKey": self.key()}

    def create_input(self, revision):
        return {"grantRevision": revision, "title": "Disposable creation conformance", "targets": [self.actor("peer")], "intentKey": self.key()}

    def closed_authority(self):
        self.owner_input = self.grant_input("creator", 0, "excluded", 1)
        for driver in (self.http, self.mcp):
            self.error(driver, "creator", "set_creation_grant", self.owner_input, "unauthorized")
            self.error(driver, "foreign_owner", "set_creation_grant", self.owner_input, "not_found")
            self.error(driver, "peer", "get_creation_grant", {"actor": self.actor("creator")}, "not_found")
            self.error(driver, "creator", "create_agent_conversation", self.create_input(1), "unauthorized")
            for choice in (None, "", "owner"):
                self.error(driver, "owner", "set_creation_grant", {**self.owner_input, "ownerReadership": choice}, "invalid")
        require(self.ok(self.http, "creator", "get_creation_grant")["revision"] == 0, "Refused input changed the grant")
        return {"noImplicitReadership": True, "ownerIsolation": True, "noImplicitScope": True}

    def excluded_creation(self):
        self.first_grant = self.ok(self.mcp, "owner", "set_creation_grant", self.owner_input)
        require(self.first_grant["revision"] == 1 and self.first_grant["duplicate"] is False, "Initial grant revision differs")
        self.excluded_input = self.create_input(1)
        self.excluded = self.ok(self.http, "creator", "create_agent_conversation", self.excluded_input)
        require(self.excluded["createdBy"] == {"actor": self.actor("creator"), "owner": self.identities["owner"]["owner"]["id"]}, "Creation attribution differs")
        require({member["actor"] for member in self.excluded["initialMembers"]} == {self.actor("creator"), self.actor("peer")}, "Excluded creation widened audience")
        require(all(member["role"] == "member" and member["historyFromSeq"] == 1 for member in self.excluded["initialMembers"]), "Initial roles or history differ")
        self.error(self.http, "owner", "read", {"conversation": self.excluded["id"]}, "not_found")
        self.error(self.mcp, "outsider", "read", {"conversation": self.excluded["id"]}, "not_found")
        require(all(row["id"] != self.excluded["id"] for row in self.ok(self.http, "owner", "list_conversations")), "Owner exclusion leaked a room title")
        return {"exactInitialAudience": True, "ownerExcluded": True, "creatorAttributed": True}

    def discovery(self):
        selector = {"collection": "creation_targets", "grantRevision": 1, "limit": 1}
        page = self.ok(self.http, "creator", "collection_page", selector)
        require(len(page["items"]) == 1 and page["next"] and page["omitted"] == {"more": True, "reason": "limit"}, "Discovery did not provide bounded continuation")
        require(len(encoded(page)) <= 65536, "Discovery exceeded the full value byte budget")
        self.cursor = page["next"]
        rest = self.ok(self.mcp, "creator", "collection_page", {**selector, "cursor": self.cursor})
        require(len(rest["items"]) == 1 and rest["next"] is None, "Discovery continuation lost a target")
        require({row["id"] for row in page["items"] + rest["items"]} == {self.actor("peer"), self.actor("spare")}, "Discovery exposed a person, caller or other owner")
        require(all(set(row) == {"id", "name", "owner", "expiresAt"} for row in page["items"] + rest["items"]), "Discovery exposed an undeclared field")
        self.error(self.mcp, "creator2", "collection_page", {**selector, "cursor": self.cursor}, "invalid")
        self.error(self.http, "peer", "collection_page", selector, "unauthorized")
        return {"boundedContinuation": True, "sameOwnerActiveOnly": True, "credentialBoundCursor": True}

    def retries_and_exchange(self):
        retry = self.ok(self.mcp, "creator2", "create_agent_conversation", self.excluded_input)
        require(retry == {**self.excluded, "duplicate": True}, "Cross-binding or credential retry changed the creation")
        self.error(self.http, "creator", "create_agent_conversation", self.create_input(1), "unauthorized")
        self.error(self.mcp, "creator", "create_agent_conversation", {**self.excluded_input, "title": "Changed"}, "conflict")
        sent = self.ok(self.http, "creator", "send", {"conversation": self.excluded["id"], "intentKey": self.key(), "text": "Fabricated agreed result"})
        received = self.ok(self.mcp, "peer", "read", {"conversation": self.excluded["id"]})
        require(received["items"][0]["id"] == sent["id"], "Peer did not receive the headless handoff")
        self.ok(self.mcp, "peer", "acknowledge", {"contributions": [sent["id"]]})
        replied = self.ok(self.mcp, "peer", "send", {"conversation": self.excluded["id"], "intentKey": self.key(), "replyTo": sent["id"], "text": "Fabricated received result"})
        history = self.ok(self.http, "creator", "read", {"conversation": self.excluded["id"]})
        require(history["items"][1]["id"] == replied["id"] and history["items"][1]["replyTo"] == sent["id"], "Linked reply changed")
        require(any(row["actor"]["id"] == self.actor("peer") for row in history["items"][0]["receivedBy"]), "Explicit receipt is missing")
        return {"sameIntentSameConversation": True, "budgetExhaustion": True, "headlessSendReceiptReply": True}

    def owner_reader(self):
        self.ok(self.http, "owner", "set_creation_grant", self.grant_input("creator", 1, "reader_from_creation"))
        self.visible = self.ok(self.mcp, "creator", "create_agent_conversation", self.create_input(2))
        require(any(row == {"actor": self.actor("owner"), "owner": self.identities["owner"]["owner"]["id"], "role": "reader", "historyFromSeq": 1} for row in self.visible["initialMembers"]), "Owner did not receive exact reader-from-creation membership")
        sent = self.ok(self.http, "creator", "send", {"conversation": self.visible["id"], "intentKey": self.key(), "text": "Visible from the beginning"})
        require(self.ok(self.mcp, "owner", "read", {"conversation": self.visible["id"]})["items"][0]["id"] == sent["id"], "Owner reader cannot see initial history")
        self.error(self.http, "owner", "send", {"conversation": self.visible["id"], "intentKey": self.key(), "text": "Reader cannot post"}, "unauthorized")
        self.error(self.http, "owner", "read", {"conversation": self.excluded["id"]}, "not_found")
        self.error(self.mcp, "creator", "collection_page", {"collection": "creation_targets", "grantRevision": 1, "cursor": self.cursor}, "unauthorized")
        return {"explicitOwnerReader": True, "noImplicitWriteAuthority": True, "noOldHistoryBackfill": True}

    def target_scope(self):
        for driver in (self.http, self.mcp):
            for target in (self.actor("outsider"), self.actor("owner"), self.actor("creator"), "act_absent"):
                self.error(driver, "creator", "create_agent_conversation", {**self.create_input(2), "targets": [target]}, "not_found")
            self.error(driver, "creator", "create_agent_conversation", {**self.create_input(2), "targets": [self.actor("peer")] * 2}, "invalid")
            self.error(driver, "creator", "create_agent_conversation", {**self.create_input(2), "ownerReadership": "excluded"}, "invalid")
        return {"uniformPrivateTargetRefusal": True, "closedAuthorityInputs": True}

    def withdrawal(self):
        args = {"actor": self.actor("creator"), "expectedRevision": 2, "intentKey": self.key()}
        first = self.ok(self.mcp, "owner", "revoke_creation_grant", args)
        require(self.ok(self.http, "owner", "revoke_creation_grant", args) == {**first, "duplicate": True}, "Withdrawal retry changed its result")
        self.error(self.mcp, "creator", "create_agent_conversation", self.create_input(2), "unauthorized")
        self.error(self.http, "creator", "create_agent_conversation", self.excluded_input, "unauthorized")
        require(len(self.ok(self.http, "peer", "read", {"conversation": self.excluded["id"]})["items"]) == 2, "Withdrawal changed an existing room")
        require(len(self.ok(self.mcp, "owner", "read", {"conversation": self.visible["id"]})["items"]) == 1, "Withdrawal removed existing readership")
        return {"futureCreationStopped": True, "existingMembershipPreserved": True}

    def nonreactivation(self):
        require(self.ok(self.mcp, "owner", "set_creation_grant", self.owner_input) == {**self.first_grant, "duplicate": True}, "Owner retry did not recover its historical mutation receipt")
        require(self.ok(self.http, "creator", "get_creation_grant")["grant"]["active"] is False, "Historical owner retry reactivated permission")
        self.spare_input = self.grant_input("spare", 0, "excluded")
        self.ok(self.http, "owner", "set_creation_grant", self.spare_input)
        self.ok(self.mcp, "owner", "revoke_creation_grant", {"actor": self.actor("spare"), "expectedRevision": 1, "intentKey": self.key()})
        return {"historicalMutationCannotReactivate": True, "withdrawnPolicyPreparedForRestart": True}

    def prepare_recovery(self):
        self.ok(self.http, "owner", "set_creation_grant", self.grant_input("creator", 3, "excluded", 1))
        self.recovery_input = self.create_input(4)
        self.recovery = self.ok(self.http, "creator", "create_agent_conversation", self.recovery_input)
        return {"acceptedCreationPreparedForRestart": True, "simulatedDiscardedResult": True}

    def recover(self):
        checkpoint = self.fixture["checkpoint"]
        recovered = self.ok(self.mcp, "creator2", "create_agent_conversation", checkpoint["recoveryInput"])
        require(recovered == {**checkpoint["recovery"], "duplicate": True}, "Restart or discarded-result retry duplicated the conversation")
        require(self.ok(self.http, "creator", "get_creation_grant")["grant"]["createdConversations"] == 1, "Restart changed the creation budget")
        self.error(self.http, "creator", "create_agent_conversation", self.create_input(4), "unauthorized")
        return {"originalCreationRecovered": True, "budgetRetained": True, "newCredentialAndBinding": True}

    def recover_withdrawal(self):
        checkpoint = self.fixture["checkpoint"]
        self.error(self.http, "spare", "create_agent_conversation", self.create_input(1), "unauthorized")
        self.ok(self.mcp, "owner", "set_creation_grant", checkpoint["spareInput"])
        current = self.ok(self.http, "spare", "get_creation_grant")
        require(current["revision"] == 2 and current["grant"]["active"] is False, "Restart or historical retry revived withdrawn permission")
        self.error(self.mcp, "owner", "read", {"conversation": checkpoint["excludedId"]}, "not_found")
        require(len(self.ok(self.http, "peer", "read", {"conversation": checkpoint["excludedId"]})["items"]) == 2, "Restart removed established history")
        return {"withdrawalRetained": True, "excludedHistoryStillPrivate": True, "existingRoomPreserved": True}


def load(path):
    source = Path(path)
    if not source.is_file() or source.stat().st_size > 65536:
        raise ConfigurationFailure("Creation fixture is missing or oversized")
    try:
        fixture = json.loads(source.read_text(encoding="utf-8"))
        require(fixture.get("creationFixtureVersion") == 1 and fixture.get("disposable") is True, "Use an explicitly disposable creation fixture")
        require(set(fixture.get("credentials", {})) == ROLES and all(isinstance(token, str) and 1 <= len(token) <= 4096 for token in fixture["credentials"].values()), "Creation fixture roles are incomplete")
        safe_endpoint(fixture["baseUrl"])
        require(fixture.get("bindings") == ["http", "mcp"], "Creation proof requires HTTP and MCP")
        return {**fixture, "conversations": {}}
    except (ValueError, TypeError, KeyError):
        raise ConfigurationFailure("Invalid creation fixture; contents withheld") from None


def main():
    parser = argparse.ArgumentParser(description="Verify the optional standing-creation extension using disposable public HTTP/MCP fixtures.")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--phase", choices=("exercise", "recovery"), default="exercise")
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    fixture = load(args.fixture)
    if args.phase == "recovery":
        checkpoint = Path(args.checkpoint)
        require(checkpoint.stat().st_size <= 65536, "Checkpoint is oversized")
        fixture["checkpoint"] = json.loads(checkpoint.read_text(encoding="utf-8"))
    suite = CreationSuite(fixture, None)
    ready = suite.test("creation-capability-and-identity", "setup", suite.preflight_creation)
    cases = [("explicit-owner-choice-and-authority", suite.closed_authority), ("owner-excluded-initial-audience", suite.excluded_creation),
             ("bounded-scoped-discovery", suite.discovery), ("retry-budget-and-headless-exchange", suite.retries_and_exchange),
             ("owner-reader-without-backfill", suite.owner_reader), ("closed-target-authority", suite.target_scope),
             ("future-only-grant-withdrawal", suite.withdrawal), ("historical-mutation-does-not-reactivate", suite.nonreactivation),
             ("accepted-intent-recovery-checkpoint", suite.prepare_recovery)] if args.phase == "exercise" else [
             ("accepted-intent-after-restart", suite.recover), ("withdrawal-and-history-after-restart", suite.recover_withdrawal)]
    for identifier, operation in cases:
        passed = suite.test(identifier, "creation", operation, skip=None if ready else "A prerequisite failed")
        ready = ready and passed
    counts = {status: sum(case["status"] == status for case in suite.cases) for status in ("passed", "failed", "skipped")}
    if ready and args.phase == "exercise":
        descriptor = os.open(args.checkpoint, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"recoveryInput": suite.recovery_input, "recovery": suite.recovery, "spareInput": suite.spare_input, "excludedId": suite.excluded["id"]}, output)
    root = Path(__file__).resolve().parent.parent
    report = {"reportFormat": "cayapa-agent-creation-conformance-1", "extensionVersion": "1", "protocolVersion": "0.2", "phase": args.phase,
              "operatorRevision": fixture.get("operatorRevision"), "observedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "endpointScope": "loopback" if suite.loopback else "https-fixture", "counts": counts, "cases": suite.cases,
              "sourceHashes": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("extensions/agent-creation-1.md", "conformance/run_creation.py", "conformance/run.py")},
              "limits": ["One fabricated operator; not independent durable operators, production deployment or actual model hosts.",
                         "Recovery phase requires a separately witnessed operator restart; the runner does not restart the service.",
                         "The exercise discards a known accepted result before recovery; it does not induce a network packet loss.",
                         "Reference tests separately cover capacity-reserved withdrawal, transaction rollback, expiry and current credential/delegation withdrawal."]}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Creation conformance: " + ", ".join(str(counts[status]) + " " + status for status in counts))
    return 0 if ready else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckFailure, ConfigurationFailure, OSError, ValueError) as error:
        print(str(error) if isinstance(error, (CheckFailure, ConfigurationFailure)) else "Creation fixture or report failed; contents withheld", file=sys.stderr)
        raise SystemExit(2)
