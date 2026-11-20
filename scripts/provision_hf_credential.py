"""Rotate the dedicated ScummHD source and Vault credential from stdin.

Run explicitly as trusted provisioning after reviewing the replacement token.
Verify the existing service before writing to the two separate APIs.
The input and provider responses stay in memory, outside logs, arguments and caches.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
import urllib.request

INSTANCE = "https://app.infisical.com"
PROJECT = "72a466bb-8c3f-482f-a214-cff243afb7e4"
ORG = "d4710ee4-0754-43d1-80f8-2970c15970c1"
BUNDLE = "5382d359-c979-4f3d-b931-701e320d9b9a"
SERVICE = "f9540a22-d6bf-4bfc-9fd2-f4a04ab4c719"
FOLDER = "/agents/huggingface-queen"
BUNDLE_NAME = "local-scummhd-queen"
SERVICE_PATH = f"/api/v1/agent-vault/services/{SERVICE}"
DATASET = "tsilva/scummhd-queen"
PATHS = {
    "/api/whoami-v2",
    *(
        f"/api/datasets/{DATASET}/{route}/main"
        for route in ("revision", "tree", "preupload", "commit")
    ),
    f"/datasets/{DATASET}/resolve/main",
}
SERVICE_METADATA = {
    "id": SERVICE,
    "name": "huggingface-queen",
    "type": "http",
    "hostPattern": "huggingface.co",
    "accessBundles": [{"id": BUNDLE, "name": BUNDLE_NAME}],
    "customHeaders": [],
    "substitutions": [],
    "variableReferences": [],
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_target(api):
    bundle = api("GET", f"/api/v1/agent-vault/access-bundles/{BUNDLE}")["accessBundle"]
    if (
        bundle["id"],
        bundle["name"],
        [entry["id"] for entry in bundle["services"]],
    ) != (BUNDLE, BUNDLE_NAME, [SERVICE]):
        raise ValueError("Unexpected Vault bundle membership")

    service = api("GET", SERVICE_PATH)["service"]
    credential = service["credential"]
    if (
        any(service.get(field) != value for field, value in SERVICE_METADATA.items())
        or set(service["allowedMethods"]) != {"GET", "HEAD", "POST"}
        or set(service["allowedPathPrefixes"]) != PATHS
        or credential["type"] != "bearer"
        or credential["headerName"].lower() != "authorization"
        or credential["headerPrefix"].strip() != "Bearer"
        or credential["memberProvidedFields"] != []
    ):
        raise ValueError("Unexpected Vault service scope")


def publish(api, value):
    projects = api("GET", "/api/v1/projects")["projects"]
    source = next((p for p in projects if p["id"] == PROJECT), {})
    if source.get("orgId") != ORG or source.get("name") != "scummhd":
        raise ValueError("Source project identity mismatch")
    verify_target(api)

    secret = api(
        "PATCH",
        "/api/v4/secrets/HF_TOKEN",
        {
            "projectId": PROJECT,
            "environment": "dev",
            "secretPath": FOLDER,
            "type": "shared",
            "secretValue": value,
        },
    )["secret"]
    if secret.get("secretKey") != "HF_TOKEN" or secret.get("environment") != "dev":
        raise ValueError("Source response mismatch; vault copy was not changed")
    del secret
    verify_target(api)
    service = api(
        "PATCH",
        SERVICE_PATH,
        {"type": "http", "credential": {"type": "bearer", "value": value}},
    )["service"]
    if service.get("id") != SERVICE or service.get("hostPattern") != "huggingface.co":
        raise ValueError("Vault response mismatch")
    verify_target(api)
    return {"source_updated": True, "vault_updated": True, "dataset": DATASET}


def provision(value):
    if not (
        re.fullmatch(r"hf_[A-Za-z0-9]{20,}", value)
        or value == "hf_scummhd_queen_unconfigured_invalid"
    ):
        raise ValueError("Invalid input format")
    cli = Path.home() / ".config/infisical/cli/0.44.13/infisical"
    result = subprocess.run(
        [
            str(cli),
            "user",
            "get",
            "token",
            "--plain",
            "--domain=" + INSTANCE,
            "--silent",
            "--telemetry=false",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode or not result.stdout.strip():
        raise ValueError("Infisical login renewal required")
    admin_token = result.stdout.strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def api(method, path, body=None):
        request = urllib.request.Request(
            INSTANCE + path,
            method=method,
            headers={
                "Authorization": "Bearer " + admin_token,
                "Content-Type": "application/json",
            },
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            error.close()
            raise

    return publish(api, value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-from-stdin", action="store_true", required=True)
    parser.parse_args()
    try:
        value = sys.stdin.read(4097).strip()
        if len(value) > 4096:
            raise ValueError("Input too large")
        print(json.dumps(provision(value)))
    except Exception:
        sys.exit(
            "Credential setup failed; provider output withheld. Source and vault may need reconciliation."
        )
