import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

from run import ConfigurationFailure, Suite, encoded, load_fixture, require


COLLECTIONS = {"agents", "conversations", "members", "invitations", "connections", "subscriptions", "receipts", "contributions", "inbox"}


class CollectionsSuite(Suite):
    def collection(self, driver, role, collection, **selectors):
        value = self.ok(driver, role, "collection_page", {"collection": collection, **selectors})
        require(isinstance(value, dict) and value.get("version") == "1" and value.get("collection") == collection, "Collection identity differs")
        require(isinstance(value.get("items"), list) and len(value["items"]) <= selectors.get("limit", 50), "Collection count exceeds the request")
        require(len(encoded(value)) <= 65536, "Complete collection value exceeds its byte limit")
        if value.get("next") is None:
            require(value.get("omitted") is None, "Completed collection still claims omissions")
        else:
            require(isinstance(value["next"], str) and 1 <= len(value["next"]) <= 2048 and value["next"].isascii(), "Continuation is malformed")
            require(value.get("omitted") in ({"more": True, "reason": "limit"}, {"more": True, "reason": "bytes"}), "Continuation has no matching omission")
        if collection in {"contributions", "inbox"}:
            require(value.get("receiptProjection") == "separate" and all("receivedBy" not in item for item in value["items"]), "Receipt projection is misleading")
        return value

    def walk_collection(self, driver, role, collection, **selectors):
        result = []
        cursor = None
        seen = set()
        for unused in range(200):
            page = self.collection(driver, role, collection, cursor=cursor, **selectors)
            result.extend(page["items"])
            if page["next"] is None:
                return result
            require(page["next"] not in seen, "Collection repeated a continuation")
            seen.add(page["next"])
            cursor = page["next"]
        raise ConfigurationFailure("Collection exceeded the disposable fixture walk limit")

    def preflight_collections(self):
        self.preflight()
        require(self.mcp is not None and self.client is not None, "Both MCP and an installed client are required for this extension proof")
        require("owner" in self.tokens and "collections" in self.conversations, "The collection extension needs its documented additional fixture roles")
        capability = self.wire.request("/capabilities", method="GET")["body"].get("capabilities", {}).get("collectionPage", {})
        advertised = set(capability.get("collections", []))
        require(capability.get("version") == "1" and capability.get("maxItems") == 50 and capability.get("maxValueBytes") == 65536
                and capability.get("cursorMaxAgeMs") == 86400000 and COLLECTIONS <= advertised, "Collection capability differs from version 1")
        if "creation_targets" in advertised:
            creation = self.wire.request("/capabilities", method="GET")["body"].get("capabilities", {}).get("agentCreation", {})
            require(creation.get("version") == "1", "Creation discovery lacks its separately declared extension")
        self.identities["owner"] = self.ok(self.http, "owner", "whoami")
        require(self.identities["owner"]["actor"]["kind"] == "person", "Collection fixture owner is not a person actor")
        return {"collections": len(COLLECTIONS), "capabilityVersion": "1"}

    def exact_bytes(self):
        body = {"text": chr(1) * 8192}
        self.first = self.send(self.http, "a", body, conversation="collections")
        self.second = self.send(self.peer, "a", body, conversation="collections")
        selector = {"conversation": self.conversations["collections"]}
        self.first_page = self.collection(self.client, "b", "contributions", **selector)
        require(len(self.first_page["items"]) == 1 and self.first_page["omitted"] == {"more": True, "reason": "bytes"}, "Escaped bodies did not use byte continuation")
        require(self.first_page["items"][0]["text"] == body["text"], "First complete legacy body changed")
        next_page = self.collection(self.peer, "b", "contributions", cursor=self.first_page["next"], **selector)
        require(len(next_page["items"]) == 1 and next_page["items"][0]["text"] == body["text"] and next_page["next"] is None, "Continuation lost or changed the second body")
        require(self.ok(self.http, "a", "send", self.first["arguments"])["duplicate"] is True, "New projection changed stored send identity")
        return {"completeLegacyBodyBytes": 8192, "separateInstalledClient": True, "bindingIndependentCursor": True}

    def all_collections(self):
        rows = {
            "agents": self.walk_collection(self.http, "owner", "agents", limit=2),
            "conversations": self.walk_collection(self.client, "b", "conversations", limit=1),
            "members": self.walk_collection(self.peer, "b", "members", conversation=self.conversations["collections"], limit=1),
            "invitations": self.walk_collection(self.http, "owner", "invitations", limit=1),
            "connections": self.walk_collection(self.client, "b", "connections", actor=self.identities["b"]["actor"]["id"], limit=1),
            "subscriptions": self.walk_collection(self.http, "owner", "subscriptions", limit=1),
            "receipts": self.walk_collection(self.peer, "b", "receipts", contribution=self.first["value"]["id"], limit=1),
            "contributions": self.walk_collection(self.client, "b", "contributions", conversation=self.conversations["collections"], limit=1),
            "inbox": self.walk_collection(self.peer, "b", "inbox", limit=1),
        }
        require(len(rows["agents"]) >= 7 and len(rows["connections"]) >= 2 and len(rows["members"]) >= 3, "Fixture did not exercise repeated collection pages")
        require(any(item["authorization"] == "revoked" for item in rows["subscriptions"]), "Archived subscription was not reachable")
        require(len(rows["contributions"]) == 2 and len({item["id"] for item in rows["contributions"]}) == 2, "Contribution traversal repeated or lost a record")
        return {"collectionsExercised": len(rows), "archivedSubscriptionReachable": True}

    def refusal(self):
        for driver in (self.http, self.peer, self.client):
            for collection in ("agents", "invitations"):
                self.error(driver, "b", "collection_page", {"collection": collection}, "unauthorized")
            for collection in ("members", "contributions"):
                self.error(driver, "outsider", "collection_page", {"collection": collection, "conversation": self.conversations["collections"]}, "not_found")
            self.error(driver, "b", "collection_page", {"collection": "connections", "actor": self.identities["a"]["actor"]["id"]}, "not_found")
            self.error(driver, "outsider", "collection_page", {"collection": "receipts", "contribution": self.first["value"]["id"]}, "not_found")
        return {"entrances": 3, "ownerAndParticipantScopesEnforced": True}

    def cursor_scope(self):
        cursor = self.first_page["next"]
        args = {"collection": "contributions", "conversation": self.conversations["collections"], "cursor": cursor}
        self.error(self.client, "b2", "collection_page", args, "invalid")
        self.error(self.peer, "a", "collection_page", args, "invalid")
        self.error(self.http, "b", "collection_page", {**args, "conversation": self.conversations["main"]}, "invalid")
        self.error(self.peer, "b", "collection_page", {**args, "collection": "members"}, "invalid")
        for malformed in ("invalid", "cp1.AA", cursor[:-2] + ("AA" if not cursor.endswith("AA") else "BB"), "x" * 2049):
            self.error(self.http, "b", "collection_page", {**args, "cursor": malformed}, "invalid")
        return {"scopeAndTamperingRejected": True}

    def history_page(self):
        history = self.fixture["history"]
        for driver in (self.http, self.peer, self.client):
            items = self.walk_collection(driver, "late", "contributions", conversation=history["conversation"], limit=1)
            require(all(item["id"] != history["hiddenContribution"] for item in items), "Withheld history leaked through a new page")
            visible = next(item for item in items if item["id"] == history["visibleContribution"])
            require(visible["replyTo"] is None and visible["replyToHidden"] is True and visible["corrects"] is None and visible["correctsHidden"] is True, "Hidden relationships leaked")
            self.error(driver, "late", "collection_page", {"collection": "receipts", "contribution": history["hiddenContribution"]}, "not_found")
        return {"bodyRelationsAndReceiptsFiltered": True}

    def withdrawn(self):
        for driver in (self.http, self.peer, self.client):
            self.error(driver, "revoked", "collection_page", {"collection": "conversations"}, "unauthorized")
            self.error(driver, "removed", "collection_page", {"collection": "contributions", "conversation": self.conversations["main"]}, "not_found")
        return {"preRevokedCredentialAndMembership": True}

    def claims(self):
        contribution = self.first["value"]["id"]
        require(self.walk_collection(self.client, "b", "receipts", contribution=contribution) == [], "A fetch created a receipt")
        before = self.walk_collection(self.client, "b", "inbox", mode="unread")
        require(any(item["id"] == contribution for item in before), "Unread collection lost an unacknowledged record")
        self.ok(self.peer, "b", "acknowledge", {"contribution": contribution})
        require(all(item["id"] != contribution for item in self.walk_collection(self.client, "b", "inbox", mode="unread")), "Acknowledged record stayed unread for its credential")
        require(any(item["id"] == contribution for item in self.walk_collection(self.client, "b2", "inbox", mode="unread")), "A different credential inherited the receipt")
        receipt = self.walk_collection(self.client, "b", "receipts", contribution=contribution)
        require(len(receipt) == 1 and receipt[0]["actor"]["id"] == self.identities["b"]["actor"]["id"], "Separated receipt attribution differs")
        return {"fetchDidNotAcknowledge": True, "connectionScopedUnread": True}

    def append_boundary(self):
        selector = {"conversation": self.conversations["collections"]}
        first = self.collection(self.client, "b", "contributions", limit=1, **selector)
        third = self.send(self.http, "a", {"text": "Created during bounded walk"}, conversation="collections")
        continuation = self.collection(self.peer, "b", "contributions", cursor=first["next"], **selector)
        require([item["id"] for item in continuation["items"]] == [self.second["value"]["id"]] and continuation["next"] is None, "Concurrent addition changed a finite walk")
        require(any(item["id"] == third["value"]["id"] for item in self.walk_collection(self.client, "b", "contributions", **selector)), "Restart did not discover a later addition")
        return {"finiteBoundary": True, "freshWalkFindsNewRecord": True}

    def wire_bounds(self):
        arguments = {"collection": "contributions", "conversation": self.conversations["collections"]}
        response = self.wire.request("/v0/collection_page", self.tokens["b"], arguments)
        require(response["status"] == 200 and response["bytes"] <= 65664 and "pendingForYou" not in response["body"], "HTTP wrapper exceeds its bound or adds optional projections")
        request = {"jsonrpc": "2.0", "id": "p" * 120, "method": "tools/call", "params": {"name": "collection_page", "arguments": arguments}}
        response = self.wire.request("/mcp", self.tokens["b"], request)
        require(response["status"] == 200 and response["bytes"] <= 200704, "MCP wrapper exceeds its bound")
        result = response["body"]["result"]
        require(json.loads(result["content"][0]["text"]) == result["structuredContent"], "MCP duplicated values disagree")
        request["id"] = "p" * 129
        refused = self.wire.request("/mcp", self.tokens["b"], request)
        require(refused["body"].get("error", {}).get("code") == -32600, "Oversized RPC identifier was not refused")
        return {"httpMaxBytes": 65664, "mcpMaxBytes": 200704}

    def invalid(self):
        for driver in (self.http, self.peer):
            for args in ({}, {"collection": "unknown"}, {"collection": "conversations", "limit": 0}, {"collection": "conversations", "limit": 51},
                         {"collection": "conversations", "surprise": True}, {"collection": "members"}, {"collection": "inbox", "mode": "future"}):
                self.error(driver, "b", "collection_page", args, "invalid")
        return {"unsupportedInputRejected": True}


def main():
    parser = argparse.ArgumentParser(description="Exercise optional collection_page/1 through HTTP, MCP and a separately installed client using disposable public-interface fixtures.")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--client-command-json", required=True)
    args = parser.parse_args()
    try:
        fixture = load_fixture(args.fixture)
        command = json.loads(args.client_command_json)
        if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
            raise ConfigurationFailure("Client command must be a nonempty argv array")
        suite = CollectionsSuite(fixture, command)
    except (ConfigurationFailure, ValueError) as error:
        parser.error(str(error) if isinstance(error, ConfigurationFailure) else "Invalid client command")
    ready = suite.test("collection-capability-and-fixture", "setup", suite.preflight_collections)
    dependency = None if ready else "Collection fixture or capability precondition failed"
    exchange = suite.test("complete-escaped-bodies-and-installed-client", "bounds", suite.exact_bytes, skip=dependency)
    dependent = dependency or (None if exchange else "Complete body exchange failed")
    for name, operation in (("all-nine-authorized-collections", suite.all_collections), ("owner-outsider-and-actor-refusals", suite.refusal),
                            ("opaque-cursor-scope-and-tampering", suite.cursor_scope), ("withheld-history-and-hidden-receipts", suite.history_page),
                            ("pre-revoked-authority", suite.withdrawn), ("separate-receipts-and-credential-unread", suite.claims),
                            ("concurrent-addition-boundary", suite.append_boundary), ("complete-http-and-mcp-wire-bounds", suite.wire_bounds),
                            ("closed-input-and-unsupported-selections", suite.invalid)):
        suite.test(name, "collections", operation, skip=dependent)
    counts = {status: sum(case["status"] == status for case in suite.cases) for status in ("passed", "failed", "skipped")}
    root = Path(__file__).resolve().parent.parent
    report = {"reportFormat": "cayapa-collection-page-conformance-1", "extensionVersion": "1", "protocolVersion": "0.2",
              "operatorRevision": fixture.get("operatorRevision"), "observedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "endpointScope": "loopback" if suite.loopback else "https-fixture", "externalClientConfigured": True,
              "sourceHashes": {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in
                               ("extensions/collection-page-1.md", "conformance/run_collections.py", "conformance/run.py")},
              "counts": counts, "cases": suite.cases,
              "limits": ["One fabricated operator with separately installed participant client; not independent-server or real-host evidence.",
                         "Owner fixture grants are pre-provisioned; this portable run reads owner collections but does not mutate owner authority.",
                         "Live owner revocation/history changes, cursor expiry/restart and deep archived history require the separate reference tests.",
                         "Legacy operations retain their documented bounds; no browser migration or global I5 claim follows."]}
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Collection conformance: " + ", ".join(str(counts[status]) + " " + status for status in counts))
    return 0 if counts == {"passed": 11, "failed": 0, "skipped": 0} else 1


if __name__ == "__main__":
    sys.exit(main())
