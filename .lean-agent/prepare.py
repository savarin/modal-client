"""IES evaluation harness for modal-client (Go SDK focus).

Read-only. Examines source code and computes IES.

Usage:
    python3 prepare.py
"""
from pathlib import Path
import re

REPO = Path("/Users/savarin/Development/python/refine/modal-client")
GO = REPO / "go"


# ════════════════════════════════════════════════════════════════════
# Scope extraction helpers (Go — regex-based, AST not available)
# ════════════════════════════════════════════════════════════════════

def _extract_go_func(content: str, name: str, receiver: str | None = None) -> str | None:
    """Extract a Go function/method body by name.

    For methods, specify receiver type (e.g., 'Client' for (c *Client)).
    Uses brace counting to find the matching closing brace.
    """
    if receiver:
        # Method: func (x *Receiver) Name(...)
        pattern = rf'func\s+\([^)]*\*?{re.escape(receiver)}\)\s+{re.escape(name)}\b'
    else:
        # Function: func Name(...)
        pattern = rf'func\s+{re.escape(name)}\b'

    match = re.search(pattern, content)
    if not match:
        return None

    # Find the opening brace
    start = match.start()
    brace_pos = content.find('{', start)
    if brace_pos == -1:
        return None

    # Count braces to find the end
    depth = 0
    for i in range(brace_pos, len(content)):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                return content[start:i + 1]
    return None


def _extract_go_func_or_method(content: str, name: str) -> str | None:
    """Extract a Go function or method by name, trying both patterns."""
    # Try as standalone function first
    result = _extract_go_func(content, name)
    if result:
        return result
    # Try as method on any receiver
    match = re.search(
        rf'func\s+\([^)]*\)\s+{re.escape(name)}\b',
        content
    )
    if match:
        start = match.start()
        brace_pos = content.find('{', start)
        if brace_pos == -1:
            return None
        depth = 0
        for i in range(brace_pos, len(content)):
            if content[i] == '{':
                depth += 1
            elif content[i] == '}':
                depth -= 1
                if depth == 0:
                    return content[start:i + 1]
    return None


# ════════════════════════════════════════════════════════════════════
# Check functions
# ════════════════════════════════════════════════════════════════════

def check_01_port_bounds_validation() -> tuple[int, str]:
    """Sandbox port values must be validated before uint32 cast.

    Go casts []int ports to uint32 without checking for negative or
    out-of-range values. Negative ports silently overflow.
    Category: input validation
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Port type is constrained (e.g., uint16, or a PortNumber newtype)
    # Check if port params use a constrained type in the struct definition
    struct_content = content
    if re.search(r'(?:EncryptedPorts|H2Ports|UnencryptedPorts)\s+\[\](?:uint16|PortNumber)\b', struct_content):
        return 3, "Port type is structurally constrained (uint16 or named type)"

    # Score 2: Runtime validation before uint32 cast
    if re.search(r'(?:port\s*[<>]=?\s*\d|port\s*<\s*0|port\s*>\s*65535|validatePort|validPort)', func_body):
        return 2, "Port values are validated before uint32 cast"

    # Score 1: Comment documents the constraint but no enforcement
    # Use \bport\b to avoid matching substrings like "supports"
    if re.search(r'//.*(?:\bport\b|uint32).*(?:valid|range|bound|negativ)', func_body, re.IGNORECASE):
        return 1, "Port range constraint documented but not enforced"

    return 0, "Ports cast to uint32 without bounds checking (negative int silently overflows)"


def check_02_volume_mount_ordering() -> tuple[int, str]:
    """Volume mounts must be deterministically ordered in the proto message.

    Go iterates over map[string]*Volume which has random order.
    Category: ordering
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Volume mount paths are sorted structurally (e.g., sorted map type,
    # or volumes stored in a slice with a sort invariant)
    if re.search(r'sort\.(?:Slice|Strings|Sort)\s*\(\s*volumeMount', func_body):
        return 3, "Volume mounts are sorted via sort package (structural)"

    # Score 2: Volume mount paths are sorted before proto construction
    if re.search(r'(?:sort|slices)\.\w+\(.*(?:mount|volume|key)', func_body, re.IGNORECASE):
        return 2, "Volume mounts are sorted before proto construction"

    # Also check for sorted key extraction pattern
    if re.search(r'keys\s*:=.*\bsort\b', func_body):
        return 2, "Volume mount keys are sorted before iteration"

    # Score 1: Comment about ordering
    if re.search(r'//.*(?:order|sort|determin)', func_body, re.IGNORECASE):
        return 1, "Volume ordering documented but not enforced"

    # Check if Volumes is NOT a map (e.g., already a slice)
    struct_match = re.search(r'Volumes\s+(\[?\]\w+)', content)
    if struct_match and 'map' not in struct_match.group(0):
        return 2, "Volumes is not a map — ordering is preserved"

    return 0, "Volume mounts iterated from map with nondeterministic order"


def check_03_cloud_bucket_mount_ordering() -> tuple[int, str]:
    """CloudBucketMounts must be deterministically ordered in the proto.

    Same nondeterminism risk as volumes — iterates over map.
    Category: ordering
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Structurally sorted
    if re.search(r'sort\.(?:Slice|Strings|Sort)\s*\(\s*cloudBucketMount', func_body):
        return 3, "CloudBucketMounts sorted via sort package (structural)"

    # Score 2: Sorted before proto construction
    if re.search(r'(?:sort|slices)\.\w+\(.*(?:bucket|cloud|mount)', func_body, re.IGNORECASE):
        return 2, "CloudBucketMounts sorted before proto construction"

    if re.search(r'keys\s*:=.*\bsort\b.*(?:bucket|cloud)', func_body, re.IGNORECASE):
        return 2, "CloudBucketMount keys sorted before iteration"

    # Score 1: Comment about ordering
    if re.search(r'//.*(?:order|sort|determin).*(?:bucket|cloud)', func_body, re.IGNORECASE):
        return 1, "CloudBucketMount ordering documented but not enforced"

    # Check if CloudBucketMounts is not a map
    struct_match = re.search(r'CloudBucketMounts\s+(\[?\]\w+)', content)
    if struct_match and 'map' not in struct_match.group(0):
        return 2, "CloudBucketMounts is not a map — ordering preserved"

    return 0, "CloudBucketMounts iterated from map with nondeterministic order"


def check_04_token_refresh_expiry_validation() -> tuple[int, str]:
    """After fetching a new auth token, expiry must be in the future.

    Neither Go nor Python validates that the server-returned token has
    expiry > now. If violated, the client enters a tight refresh loop.
    Category: input validation
    """
    content = (GO / "auth_token_manager.go").read_text()
    func_body = _extract_go_func_or_method(content, "FetchToken")
    if not func_body:
        return 0, "Cannot find FetchToken"

    # Score 3: Expiry type enforces future time (e.g., FutureTimestamp newtype)
    if re.search(r'FutureTimestamp|FutureExpiry|NewFutureTime', func_body):
        return 3, "Expiry uses a future-time type (structural)"

    # Score 2: Runtime check that expiry > now after fetch
    if re.search(r'expiry\s*[<>]=?\s*(?:time\.Now|now)', func_body):
        return 2, "Expiry validated to be in the future after fetch"

    if re.search(r'if\s+exp\w*\s*<=?\s*(?:time\.Now|now|0)', func_body):
        return 2, "Expiry checked to be positive/future"

    # Score 1: Comment about expiry requirements
    if re.search(r'//.*(?:expiry|expire).*(?:future|valid|positive)', func_body, re.IGNORECASE):
        return 1, "Expiry requirement documented but not enforced"

    return 0, "Token expiry not validated after fetch (tight refresh loop risk)"


def check_05_profile_credentials_validation() -> tuple[int, str]:
    """Profile should validate credentials at construction, not at first RPC.

    Go checks in injectRequiredHeaders (RPC time). Errors surface
    only when the first RPC is attempted.
    Category: input validation
    """
    content = (GO / "config.go").read_text()
    get_profile = _extract_go_func(content, "getProfile")
    if not get_profile:
        return 0, "Cannot find getProfile"

    # Score 3: Profile type requires non-empty credentials at construction
    # (e.g., constructor returns error if empty)
    client_content = (GO / "client.go").read_text()
    new_client = _extract_go_func(client_content, "NewClientWithOptions")

    if new_client and re.search(r'(?:profile\.TokenID|tokenID)\s*==\s*"".*(?:return\s+nil|error|fmt\.Errorf)', new_client, re.DOTALL):
        return 3, "Credentials validated at client construction (structural)"

    # Score 2: Validation in getProfile or NewClientWithOptions
    if get_profile and re.search(r'(?:TokenID|TokenSecret)\s*==\s*""', get_profile):
        return 2, "Credentials validated in getProfile"

    if new_client and re.search(r'(?:token|credential).*(?:empty|missing|required)', new_client, re.IGNORECASE):
        return 2, "Credentials validated at client construction"

    # Score 1: Documented in comments
    all_content = content + (client_content if new_client else "")
    if re.search(r'//.*(?:token|credential).*(?:required|must|needed)', all_content, re.IGNORECASE):
        return 1, "Credential requirement documented but deferred to RPC time"

    return 0, "Credentials not validated until first RPC call"


def check_06_timeout_zero_value() -> tuple[int, str]:
    """Timeout=0 should produce a clear error or documented default, not silent mapping.

    Go maps 0 → 300 with only a comment. Users who intend "no timeout"
    get 5 minutes silently.
    Category: contract consistency
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Timeout type prevents zero (e.g., NonZeroDuration, or Option type
    # where None means "use default" and Some(0) is rejected)
    if re.search(r'(?:NonZero|Positive)Duration|OptionalTimeout', content):
        return 3, "Timeout type structurally prevents zero-value ambiguity"

    # Check if Timeout uses a pointer type (nil = default, 0 = explicit zero)
    struct_def = re.search(r'Timeout\s+\*time\.Duration', content)
    if struct_def:
        return 3, "Timeout uses *time.Duration (nil = default, 0 = explicit)"

    # Score 2: Runtime check with error or warning for explicit zero
    if re.search(r'(?:warn|log|fmt\.Print).*(?:timeout|Timeout).*(?:zero|0|default)', func_body, re.IGNORECASE):
        return 2, "Zero timeout produces a warning"

    # Score 1: Comment documents the ambiguity
    if re.search(r'//.*(?:zero|0).*(?:timeout|default|ambig)', func_body, re.IGNORECASE):
        return 1, "Zero-value timeout ambiguity documented in comment"

    return 0, "Timeout=0 silently maps to 300 seconds without warning"


def check_07_cpu_request_validation() -> tuple[int, str]:
    """CPU request must be positive and CPU limit >= CPU request.

    Both Go and Python validate this. Check enforcement quality.
    Category: input validation
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    has_positive_check = bool(re.search(r'CPU.*<=\s*0|CPU.*must.*positive', func_body))
    has_limit_check = bool(re.search(r'CPULimit\s*<\s*(?:params\.)?CPU|CPULimit.*cannot.*higher', func_body))
    has_requires_request = bool(re.search(r'CPU\s*==\s*0\s*&&.*CPULimit|must.*specify.*CPU.*request', func_body))

    # Score 3: CPU is a typed value that structurally prevents invalid values
    if re.search(r'PositiveCPU|CPUCores\b|type\s+CPU\s+', content):
        return 3, "CPU uses a constrained type (structural)"

    # Score 2: All three validations present as runtime checks
    if has_positive_check and has_limit_check and has_requires_request:
        return 2, "CPU validated: positive, limit >= request, limit requires request"

    # Two of three
    checks_found = sum([has_positive_check, has_limit_check, has_requires_request])
    if checks_found >= 2:
        return 2, f"CPU partially validated ({checks_found}/3 checks present)"

    if checks_found >= 1:
        return 1, f"CPU has {checks_found}/3 validation checks"

    return 0, "CPU not validated before proto construction"


def check_08_memory_request_validation() -> tuple[int, str]:
    """Memory request must be positive and memory limit >= memory request.

    Category: input validation
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    has_positive = bool(re.search(r'MemoryMiB.*<=\s*0|MemoryMiB.*must.*positive', func_body))
    has_limit = bool(re.search(r'MemoryLimitMiB\s*<\s*(?:params\.)?MemoryMiB|MemoryLimitMiB.*cannot.*higher', func_body))
    has_requires = bool(re.search(r'MemoryMiB\s*==\s*0\s*&&.*MemoryLimitMiB|must.*specify.*MemoryMiB', func_body))

    # Score 3: Memory uses a constrained type
    if re.search(r'PositiveMemory|MemoryMiB\b.*type|type\s+MemoryMiB\s+', content):
        return 3, "Memory uses a constrained type (structural)"

    # Score 2: All validations present
    checks = sum([has_positive, has_limit, has_requires])
    if checks >= 2:
        return 2, f"Memory validated ({checks}/3 checks present)"

    if checks >= 1:
        return 1, f"Memory has {checks}/3 validation checks"

    return 0, "Memory not validated before proto construction"


def check_09_workdir_absolute_path() -> tuple[int, str]:
    """Workdir must be an absolute path (start with /).

    Both Go and Python enforce this.
    Category: input validation
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Workdir type enforces absolute paths (e.g., AbsolutePath newtype)
    if re.search(r'AbsolutePath|AbsPath|type\s+Workdir\s+', content):
        return 3, "Workdir uses a structurally-constrained absolute path type"

    # Score 2: Runtime check with error return
    if re.search(r'(?:HasPrefix|startsWith|strings\.HasPrefix)\s*\(\s*(?:params\.)?[Ww]orkdir.*"/"', func_body):
        return 2, "Workdir validated as absolute path with HasPrefix check"

    if re.search(r'Workdir.*!.*"/".*error|Workdir.*must.*absolute', func_body):
        return 2, "Workdir validated as absolute path with error"

    # Score 1: Documented
    if re.search(r'//.*[Ww]orkdir.*absolute', func_body):
        return 1, "Absolute path requirement documented but not enforced"

    return 0, "Workdir not validated as absolute path"


def check_10_network_access_mutual_exclusion() -> tuple[int, str]:
    """BlockNetwork and CIDRAllowlist are mutually exclusive.

    Category: contract consistency
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Network access uses a sum type (enum/union) that structurally
    # prevents both being set
    if re.search(r'NetworkAccessMode|type\s+NetworkAccess\s+(?:int|string)', content):
        return 3, "Network access uses a sum type preventing invalid combinations"

    # Score 2: Runtime mutual exclusion check with error
    if re.search(r'BlockNetwork.*CIDRAllowlist|CIDRAllowlist.*BlockNetwork', func_body):
        return 2, "BlockNetwork/CIDRAllowlist mutual exclusion enforced"

    if re.search(r'cannot.*used.*Block|BlockNetwork.*enabled.*CIDR', func_body, re.IGNORECASE):
        return 2, "Mutual exclusion enforced with error message"

    # Score 1: Documented
    if re.search(r'//.*(?:mutual|exclusive|cannot.*both)', func_body, re.IGNORECASE):
        return 1, "Mutual exclusion documented but not enforced"

    return 0, "BlockNetwork and CIDRAllowlist not checked for mutual exclusion"


def check_11_server_url_scheme_validation() -> tuple[int, str]:
    """ServerURL must have https:// or http:// scheme.

    Go validates in newClient. Invalid URLs produce a gRPC error.
    Category: type safety
    """
    content = (GO / "client.go").read_text()
    func_body = _extract_go_func(content, "newClient")
    if not func_body:
        return 0, "Cannot find newClient"

    # Score 3: ServerURL is a typed value that parses at construction
    config_content = (GO / "config.go").read_text()
    if re.search(r'type\s+ServerURL\s+struct|ParseServerURL|NewServerURL', config_content):
        return 3, "ServerURL is a structured type parsed at construction"

    # Also check if Profile.ServerURL is a custom type (not string)
    if re.search(r'ServerURL\s+ServerURL\b', config_content):
        return 3, "ServerURL is a named type in Profile struct"

    # Score 2: Validated at connection time with error
    if re.search(r'https://|http://', func_body) and re.search(r'(?:invalid|error|Errorf).*(?:server|URL|url)', func_body, re.IGNORECASE):
        return 2, "ServerURL scheme validated at connection time with error"

    # Score 1: Partial validation or documented
    if re.search(r'https://|http://', func_body):
        return 1, "ServerURL scheme checked but error handling unclear"

    return 0, "ServerURL scheme not validated"


def check_12_close_idempotency() -> tuple[int, str]:
    """Client.Close() must be safe to call multiple times.

    Go's Close() closes cpClient and iterates ipClients under lock.
    A second call should not panic on nil or double-close.
    Category: resource management
    """
    content = (GO / "client.go").read_text()
    func_body = _extract_go_func(content, "Close", receiver="Client")
    if not func_body:
        return 0, "Cannot find Client.Close"

    # Score 3: Close uses sync.Once or sets a "closed" flag checked structurally
    if re.search(r'sync\.Once|once\.Do|atomic\..*closed|closed\.Store', func_body):
        return 3, "Close uses sync.Once or atomic closed flag (structural)"

    if re.search(r'once\b.*Close|closeOnce', content):
        return 3, "Close wrapped in sync.Once"

    # Score 2: Nil check before closing, and map reset prevents double-close
    has_nil_check = bool(re.search(r'cpClient\s*!=\s*nil', func_body))
    has_map_reset = bool(re.search(r'ipClients\s*=\s*map', func_body))

    if has_nil_check and has_map_reset:
        return 2, "Close guards against nil cpClient and resets ipClients map"

    if has_nil_check:
        return 2, "Close guards against nil cpClient"

    # Score 1: Partial guard
    if has_map_reset:
        return 1, "ipClients map reset but cpClient not guarded for double-close"

    return 0, "Close() may panic on double-call or nil client"


def check_13_secret_nil_handling() -> tuple[int, str]:
    """Nil or empty secrets in sandbox params must produce errors, not be silently skipped.

    Go sandbox.go silently skips nil secrets: `if secret != nil { ... }`.
    A user who puts a nil *Secret in the Secrets slice gets no error —
    the secret is silently dropped and the sandbox starts without it.
    Category: input validation (invisible when broken)
    """
    content = (GO / "sandbox.go").read_text()
    func_body = _extract_go_func(content, "buildSandboxCreateRequestProto")
    if not func_body:
        return 0, "Cannot find buildSandboxCreateRequestProto"

    # Score 3: Secrets use a non-nil type (e.g., []*Secret becomes []Secret,
    # or a NonNilSecret wrapper type)
    if re.search(r'\[\]Secret\b(?!\s*\*)', content) and not re.search(r'\[\]\*Secret', content):
        return 3, "Secrets use value type []Secret — nil elements impossible (structural)"

    # Also check for a wrapper type
    if re.search(r'type\s+NonNil\w*Secret|type\s+SecretRef\s+struct', content):
        return 3, "Secrets use a non-nil wrapper type (structural)"

    # Score 2: Nil check produces an error instead of silently skipping
    if re.search(r'secret\s*==\s*nil.*(?:error|Errorf|return\s+nil)', func_body, re.DOTALL):
        return 2, "Nil secrets produce an error (validated)"

    if re.search(r'nil.*secret.*(?:error|invalid|must)', func_body, re.IGNORECASE):
        return 2, "Nil secrets are rejected with an error"

    # Score 1: Nil check exists (even if it silently skips)
    if re.search(r'secret\s*!=\s*nil', func_body):
        return 1, "Nil secrets are filtered but silently skipped (no error)"

    return 0, "No nil-secret handling — nil secrets could cause panic"


INVARIANTS = [
    ("port_bounds_validation", check_01_port_bounds_validation),
    ("volume_mount_ordering", check_02_volume_mount_ordering),
    ("cloud_bucket_ordering", check_03_cloud_bucket_mount_ordering),
    ("token_refresh_expiry", check_04_token_refresh_expiry_validation),
    ("profile_credentials", check_05_profile_credentials_validation),
    ("timeout_zero_value", check_06_timeout_zero_value),
    ("cpu_request_validation", check_07_cpu_request_validation),
    ("memory_request_validation", check_08_memory_request_validation),
    ("workdir_absolute_path", check_09_workdir_absolute_path),
    ("network_mutual_exclusion", check_10_network_access_mutual_exclusion),
    ("server_url_scheme", check_11_server_url_scheme_validation),
    ("close_idempotency", check_12_close_idempotency),
    ("secret_nil_handling", check_13_secret_nil_handling),
]

LEVEL_NAMES = {3: "structural", 2: "validated", 1: "convention", 0: "unguarded"}


def main() -> None:
    results = []
    for name, check_fn in INVARIANTS:
        score, explanation = check_fn()
        results.append((name, score, explanation))

    print("=" * 78)
    print(f"{'Invariant':<28} {'Score':<6} {'Level':<12} Explanation")
    print("-" * 78)
    for name, score, explanation in results:
        level = LEVEL_NAMES[score]
        print(f"{name:<28} {score:<6} {level:<12} {explanation}")
    print("=" * 78)

    scores = [r[1] for r in results]
    n = len(scores)
    total = sum(scores)
    ies = total / (3 * n) if n > 0 else 0

    print()
    print(f"ies_score: {ies:.4f}")
    print(f"ies_numerator: {total}")
    print(f"ies_denominator: {3 * n}")
    print(f"invariant_count: {n}")
    print(f"structural_count: {sum(1 for s in scores if s == 3)}")
    print(f"validated_count: {sum(1 for s in scores if s == 2)}")
    print(f"convention_count: {sum(1 for s in scores if s == 1)}")
    print(f"unguarded_count: {sum(1 for s in scores if s == 0)}")


if __name__ == "__main__":
    main()
