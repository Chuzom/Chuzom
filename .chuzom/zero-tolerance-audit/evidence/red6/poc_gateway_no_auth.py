"""RED-6 PoC (sandboxed, no live network): does gateway.py's ONLY protection
(is_forbidden_cross_origin, the CSRF/DNS-rebinding guard) actually function as
authentication against a non-browser client hitting a gateway that is bound to
0.0.0.0 (the shipped "team-server" preset) or otherwise reachable over a
network? We call the real function directly with header dicts shaped exactly
like what curl / python-requests / the OpenAI or Anthropic SDK naturally send
-- no Origin, no Referer, just a Host header -- and also simulate what a
REMOTE (non-loopback) client would send when CHUZOM_ALLOWED_HOSTS has been
widened (as it must be for the 0.0.0.0 preset to be usable by remote team
members at all, since otherwise the Host check itself blocks everyone).
"""
import os
import sys

sys.path.insert(0, "/private/tmp/claude-501/-Users-yaliandrona-Projects-llm-router/b006765e-249f-49a4-a54c-c3030f141d78/scratchpad/AUDIT-c2c2882/src")

from chuzom.route_server import is_forbidden_cross_origin, _LOCAL_HOSTS  # noqa: E402

print("=== _LOCAL_HOSTS (the built-in allowlist) ===", sorted(_LOCAL_HOSTS))
print()

# Case 1: a non-browser client (curl, python requests, the OpenAI/Anthropic SDK)
# hitting a LOOPBACK-bound gateway. This is the "legitimate" traffic the guard's
# own docstring says is "unaffected".
headers_curl_loopback = {"Host": "127.0.0.1:17900", "User-Agent": "curl/8.4.0"}
print("Case 1: curl-style request, Host=127.0.0.1:17900, no Origin/Referer")
print("  is_forbidden_cross_origin ->", is_forbidden_cross_origin(headers_curl_loopback))
print("  (False == request PASSES THROUGH with zero credentials presented)")
print()

# Case 2: same shape, but the caller is a malicious LOCAL process/script (not a
# browser) that also simply sets Host: 127.0.0.1. Indistinguishable from Case 1
# to this guard -- because the guard was never designed to distinguish "my own
# CLI" from "any other local process"; it is a browser/DNS-rebinding-specific
# check, not an identity/auth check.
headers_malicious_local_script = {"Host": "127.0.0.1:17900"}
print("Case 2: a hostile local script/process, Host=127.0.0.1:17900, no Origin/Referer")
print("  is_forbidden_cross_origin ->", is_forbidden_cross_origin(headers_malicious_local_script))
print("  (False == indistinguishable from 'legitimate' traffic; guard has no")
print("   notion of caller identity at all)")
print()

# Case 3: the "team-server" preset scenario. presets.py ships host=0.0.0.0 for
# this preset. For ANY remote machine's HTTP client to actually reach it usefully
# it must send Host: <server-ip-or-hostname>:17900 (that's how HTTP addressing
# works -- the client sets Host to whatever it dialed). Since <server-ip> is NOT
# in the default _LOCAL_HOSTS, out of the box this WOULD be rejected -- UNLESS
# the operator sets CHUZOM_ALLOWED_HOSTS to include that host (which they must,
# for the preset to be usable by remote teammates at all). We simulate that
# post-configuration state, which is the only state in which the "team-server"
# preset actually functions as advertised.
os.environ["CHUZOM_ALLOWED_HOSTS"] = "10.0.0.5"
headers_remote_client_after_widening = {"Host": "10.0.0.5:17900"}
print("Case 3: remote non-browser client, Host=10.0.0.5:17900, CHUZOM_ALLOWED_HOSTS=10.0.0.5")
print("  (this is the state an operator MUST reach for the built-in team-server")
print("   preset, host=0.0.0.0, to be usable by any remote teammate at all)")
print("  is_forbidden_cross_origin ->", is_forbidden_cross_origin(headers_remote_client_after_widening))
print("  (False == ANY client on the network -- friend or attacker -- that")
print("   simply sets Host: 10.0.0.5:17900 and omits Origin/Referer reaches")
print("   /v1/chat/completions etc. with ZERO credentials, ZERO auth check)")
print()

del os.environ["CHUZOM_ALLOWED_HOSTS"]
print("=== CONCLUSION ===")
print("is_forbidden_cross_origin() never inspects any credential, API key, bearer")
print("token, or client identity -- only Host/Origin/Referer, all of which are")
print("attacker-controlled request headers with no secret material. It cannot")
print("function as authentication. gateway.py has ZERO Depends()-based auth on")
print("any route (grep-confirmed separately). Combined with the built-in")
print("'team-server' preset (host=0.0.0.0) and no _allow_public_bind()-style")
print("runtime refusal gate anywhere in gateway.py/presets.py, this proves a")
print("real-money-spending network exposure once that preset (or")
print("CHUZOM_GATEWAY_HOST) is used.")
