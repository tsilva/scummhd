"""Fixed read-only checks. Run through hf_vault.py, never with a real HF_TOKEN."""
import errno
import json
import os
from pathlib import Path
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request


def status(method, path):
    request = urllib.request.Request("https://huggingface.co" + path, method=method,
        headers={"Authorization": "Bearer hf_scummhd_queen_proxy_placeholder"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(1024 * 1024)
            return response.status, json.loads(body) if response.status == 200 else None
    except urllib.error.HTTPError as error:
        return error.code, None


def denied(call):
    try:
        call()
    except OSError as error:
        return error.errno in (errno.EPERM, errno.EACCES)
    return False


def main():
    action, temp, home = sys.argv[1:]
    checks = {}
    checks["placeholder_only"] = os.environ.get("HF_TOKEN") == "hf_scummhd_queen_proxy_placeholder"
    proxy = urllib.parse.urlsplit(os.environ.get("HTTPS_PROXY", os.environ.get("https_proxy", "")))
    checks["pinned_local_proxy"] = proxy.hostname == "127.0.0.1" and proxy.port == 8283
    if not all(checks.values()):
        return checks
    os.environ.pop("NO_PROXY", None)
    os.environ.pop("no_proxy", None)
    if action == "test-policy":
        checks["direct_network_denied"] = denied(lambda: socket.create_connection(("1.1.1.1", 443), 2))
        checks["admin_files_denied"] = denied(lambda: (Path(home) / ".config/infisical/agent-vault-ca.pem").read_bytes())
        checks["project_writes_denied"] = denied(lambda: (Path(__file__).parent / ".sandbox-write-test").write_text("fake"))
        for name, method, path in [
            ("other_service_denied", "GET", "/api/models/gpt2"),
            ("similar_repository_denied", "GET", "/api/datasets/tsilva/scummhd-queen-other/revision/main"),
            ("delete_denied", "DELETE", "/api/datasets/tsilva/scummhd-queen/revision/main"),
        ]:
            code, _ = status(method, path)
            checks[name] = code == 403
        code, _ = status("GET", "/api/whoami-v2")
        checks["invalid_setup_key_rejected"] = code == 401
    else:
        code, identity = status("GET", "/api/whoami-v2")
        checks["authenticated_as_tsilva"] = code == 200 and identity.get("name") == "tsilva"
    return checks


if __name__ == "__main__":
    try:
        checks = main()
    except Exception:
        checks = {"transport_succeeded": False}
    print("SCUMMHD_RESULT " + json.dumps(checks))
    sys.exit(0 if checks and all(checks.values()) else 1)
