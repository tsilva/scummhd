"""Trusted administration only: stdin -> dedicated source slot + Agent Vault.

Run explicitly after credential creation/rotation; never from an ordinary client.
The input and provider responses stay in memory, outside logs, arguments and caches.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

INSTANCE = "https://app.infisical.com"
PROJECT = "72a466bb-8c3f-482f-a214-cff243afb7e4"
ORG = "d4710ee4-0754-43d1-80f8-2970c15970c1"
BUNDLE = "5382d359-c979-4f3d-b931-701e320d9b9a"
SERVICE = "f9540a22-d6bf-4bfc-9fd2-f4a04ab4c719"
FOLDER = "/agents/huggingface-queen"


def provision(value):
    if not (re.fullmatch(r"hf_[A-Za-z0-9]{20,}", value) or
            value == "hf_scummhd_queen_unconfigured_invalid"):
        raise ValueError("Invalid input format")
    cli = Path.home() / ".config/infisical/cli/0.44.13/infisical"
    result = subprocess.run([str(cli), "user", "get", "token", "--plain",
        "--domain=" + INSTANCE, "--silent", "--telemetry=false"],
        capture_output=True, text=True, timeout=30)
    if result.returncode or not result.stdout.strip():
        raise ValueError("Infisical login renewal required")
    admin_token = result.stdout.strip()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(method, path, body=None):
        request = urllib.request.Request(INSTANCE + path, method=method,
            headers={"Authorization": "Bearer " + admin_token, "Content-Type": "application/json"},
            data=None if body is None else json.dumps(body).encode())
        with opener.open(request, timeout=30) as response:
            return json.load(response)

    projects = api("GET", "/api/v1/projects")["projects"]
    source = next((p for p in projects if p["id"] == PROJECT), {})
    if source.get("orgId") != ORG or source.get("name") != "scummhd":
        raise ValueError("Source project identity mismatch")
    secret = api("PATCH", "/api/v4/secrets/HF_TOKEN", {
        "projectId": PROJECT, "environment": "dev", "secretPath": FOLDER,
        "type": "shared", "secretValue": value})["secret"]
    if secret.get("secretKey") != "HF_TOKEN" or secret.get("environment") != "dev":
        raise ValueError("Source response mismatch; vault copy was not changed")
    del secret
    service = api("PATCH", f"/api/v1/agent-vault/access-bundles/{BUNDLE}/services/{SERVICE}", {
        "type": "http", "credential": {"type": "bearer", "value": value}})["service"]
    if service.get("id") != SERVICE or service.get("hostPattern") != "huggingface.co":
        raise ValueError("Vault response mismatch")
    return {"source_updated": True, "vault_updated": True, "dataset": "tsilva/scummhd-queen"}


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
        sys.exit("Credential setup failed; provider output withheld. Source and vault may need reconciliation.")
