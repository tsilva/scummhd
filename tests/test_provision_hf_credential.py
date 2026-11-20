from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from subprocess import CompletedProcess
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import provision_hf_credential as provision


TOKEN = "hf_" + "a" * 20
ADMIN = "synthetic-admin"
SOURCE_PATH = "/api/v4/secrets/HF_TOKEN"
BUNDLE_PATH = f"/api/v1/agent-vault/access-bundles/{provision.BUNDLE}"
MEMBERSHIP = {"id": provision.BUNDLE, "name": provision.BUNDLE_NAME}


class Catalog(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.requests.append(("GET", self.path))
        if self.server.redirect:
            self.send_response(302)
            self.send_header("Location", "/unexpected")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/api/v1/projects":
            value = {
                "projects": [
                    {"id": provision.PROJECT, "orgId": provision.ORG, "name": "scummhd"}
                ]
            }
        elif self.path == BUNDLE_PATH:
            value = {
                "accessBundle": {**MEMBERSHIP, "services": [{"id": provision.SERVICE}]}
            }
        elif self.path == provision.SERVICE_PATH:
            value = {"service": self.server.service}
        else:
            self.send_error(404)
            return
        self.reply(value)

    def do_PATCH(self):
        self.server.requests.append(("PATCH", self.path))
        length = int(self.headers["Content-Length"])
        self.server.writes.append((self.path, json.loads(self.rfile.read(length))))
        if self.path == SOURCE_PATH:
            if self.server.change_after_source:
                self.server.service["allowedMethods"].append("DELETE")
            self.reply({"secret": {"secretKey": "HF_TOKEN", "environment": "dev"}})
        elif self.path == provision.SERVICE_PATH:
            self.reply({"service": self.server.service})
        else:
            self.send_error(404)

    def reply(self, value):
        if self.headers.get("Authorization") != f"Bearer {ADMIN}":
            self.send_error(401)
            return
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        server = self.server = HTTPServer(("127.0.0.1", 0), Catalog)
        self.addCleanup(server.server_close)
        server.requests = []
        server.writes = []
        server.redirect = False
        server.change_after_source = False
        server.service = {
            "id": provision.SERVICE,
            "name": "huggingface-queen",
            "type": "http",
            "hostPattern": "huggingface.co",
            "allowedMethods": ["GET", "HEAD", "POST"],
            "allowedPathPrefixes": sorted(provision.PATHS),
            "accessBundles": [deepcopy(MEMBERSHIP)],
            "customHeaders": [],
            "substitutions": [],
            "variableReferences": [],
            "credential": {
                "type": "bearer",
                "headerName": "Authorization",
                "headerPrefix": "Bearer",
                "memberProvidedFields": [],
            },
        }
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        self.enterContext(
            patch.object(
                provision, "INSTANCE", f"http://127.0.0.1:{server.server_port}"
            )
        )
        self.enterContext(
            patch.object(
                provision.subprocess,
                "run",
                return_value=CompletedProcess([], 0, ADMIN, ""),
            )
        )

    def test_writes_only_existing_source_and_service_bearer(self):
        outcome = provision.provision(TOKEN)
        self.assertEqual(
            outcome,
            {
                "source_updated": True,
                "vault_updated": True,
                "dataset": provision.DATASET,
            },
        )
        self.assertEqual(
            self.server.writes,
            [
                (
                    SOURCE_PATH,
                    {
                        "projectId": provision.PROJECT,
                        "environment": "dev",
                        "secretPath": provision.FOLDER,
                        "type": "shared",
                        "secretValue": TOKEN,
                    },
                ),
                (
                    provision.SERVICE_PATH,
                    {"type": "http", "credential": {"type": "bearer", "value": TOKEN}},
                ),
            ],
        )
        self.assertEqual(
            self.server.requests[:3],
            [
                ("GET", "/api/v1/projects"),
                ("GET", BUNDLE_PATH),
                ("GET", provision.SERVICE_PATH),
            ],
        )

    def test_unexpected_membership_refuses_both_writes(self):
        self.server.service["accessBundles"].append(
            {"id": "another", "name": "unreviewed"}
        )
        with self.assertRaisesRegex(ValueError, "service scope"):
            provision.provision(TOKEN)
        self.assertEqual(self.server.writes, [])

    def test_drift_between_writes_stops_the_vault_update(self):
        self.server.change_after_source = True
        with self.assertRaisesRegex(ValueError, "service scope"):
            provision.provision(TOKEN)
        self.assertEqual([path for path, _ in self.server.writes], [SOURCE_PATH])

    def test_does_not_follow_admin_redirects(self):
        self.server.redirect = True
        with self.assertRaises(HTTPError) as error:
            provision.provision(TOKEN)
        self.assertEqual(error.exception.code, 302)
        self.assertEqual(self.server.requests, [("GET", "/api/v1/projects")])
