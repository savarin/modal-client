"""IES evaluation harness for modal-client.

Read-only. Examines source code and computes IES.

Usage:
    python3 prepare.py
"""
from pathlib import Path
import ast
import re

REPO = Path("/Users/savarin/Development/python/refine/modal-client")
SRC = REPO / "py" / "modal"


# ════════════════════════════════════════════════════════════════════
# Check functions
# ════════════════════════════════════════════════════════════════════


def check_01_initialize_from_other_hydration_guard() -> tuple[int, str]:
    """_initialize_from_other must validate source is hydrated before copying _object_id."""
    content = (SRC / "_object.py").read_text()

    # Extract _initialize_from_other method body
    match = re.search(
        r"def\s+_initialize_from_other\(.*?\).*?(?=\n    def\s|\nclass\s|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return 0, "_initialize_from_other not found"

    body = match.group()

    # Score 3: structural — uses a type that prevents unhydrated access
    # e.g., object_id is a non-optional typed field, or uses a HydratedObject type
    if re.search(r"HydratedObject|@dataclass.*frozen|NewType.*ObjectId", body, re.DOTALL):
        return 3, "Structural: typed wrapper prevents unhydrated access"

    # Score 2: validated — explicit hydration check before copying
    if re.search(
        r"(_validate_is_hydrated|is_hydrated|_is_hydrated|assert\s+.*hydrat|if\s+not\s+.*hydrat|\.object_id\b)",
        body,
    ):
        # Check specifically: does it use .object_id (property with guard) or ._object_id (raw)?
        uses_property = re.search(r"other\.object_id\b(?!_)", body)
        uses_raw = re.search(r"other\._object_id", body)
        if uses_property and not uses_raw:
            return 2, "Validated: uses .object_id property which raises on None"
        if re.search(r"_validate_is_hydrated|assert.*hydrat|if\s+not\s+.*_is_hydrated", body):
            return 2, "Validated: explicit hydration check before copy"

    # Score 1: convention — comment or docstring mentions hydration requirement
    if re.search(r"#.*hydrat|\"\"\".*hydrat", body, re.IGNORECASE):
        return 1, "Convention: documented but not enforced"

    # Score 0: unguarded — copies _object_id directly
    if re.search(r"\._object_id\s*=\s*other\._object_id", body):
        return 0, "Unguarded: copies _object_id directly without hydration check"

    return 0, "Unguarded: no hydration validation found"


def check_02_prefix_validation_consistency() -> tuple[int, str]:
    """Prefix validation in _hydrate and _new_hydrated must use the same pattern."""
    content = (SRC / "_object.py").read_text()

    # Extract _hydrate method
    hydrate_match = re.search(
        r"def\s+_hydrate\(self.*?\).*?(?=\n    def\s|\n    @|\nclass\s|\Z)",
        content,
        re.DOTALL,
    )
    # Extract _new_hydrated method
    new_hydrated_match = re.search(
        r"def\s+_new_hydrated\(.*?\).*?(?=\n    def\s|\n    @|\nclass\s|\Z)",
        content,
        re.DOTALL,
    )

    if not hydrate_match or not new_hydrated_match:
        return 0, "Could not find both _hydrate and _new_hydrated methods"

    hydrate_body = hydrate_match.group()
    new_hydrated_body = new_hydrated_match.group()

    # Score 3: structural — shared validation function or typed ObjectId with prefix
    if re.search(r"_validate_prefix|validate_object_id|ObjectId\(", content):
        return 3, "Structural: shared validation function for prefix checking"

    # Score 2: validated — both methods use the same startswith pattern
    hydrate_pattern = re.search(r'startswith\((.*?)\)', hydrate_body)
    new_hydrated_pattern = re.search(r'startswith\((.*?)\)', new_hydrated_body)

    if hydrate_pattern and new_hydrated_pattern:
        h_arg = hydrate_pattern.group(1).strip()
        n_arg = new_hydrated_pattern.group(1).strip()
        # Check if both use the stricter pattern (prefix + "-")
        both_strict = '"-"' in h_arg and '"-"' in n_arg
        both_strict = both_strict or ('+' in h_arg and '+' in n_arg)
        if both_strict:
            return 2, "Validated: both use consistent prefix+dash pattern"
        else:
            return 1, f"Convention: inconsistent patterns — _hydrate uses {h_arg}, _new_hydrated uses {n_arg}"

    # Score 1: at least both check something
    if hydrate_pattern or new_hydrated_pattern:
        return 1, "Convention: only one method validates prefix consistently"

    return 0, "Unguarded: no prefix validation found"


def check_03_grpc_status_mapping_safety() -> tuple[int, str]:
    """gRPC error converter must handle all status codes safely (no KeyError)."""
    content = (SRC / "_grpc_client.py").read_text()

    # Extract grpc_error_converter __exit__ method
    match = re.search(
        r"class\s+grpc_error_converter.*?(?=\nclass\s|\n[A-Z_]|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return 0, "grpc_error_converter not found"

    body = match.group()

    # Score 3: structural — exhaustive match via enum dispatch, or type-safe mapping
    # e.g., using a match statement on all Status values, or TypedDict
    if re.search(r"match\s+exc\.status|Literal\[Status\.\w+\]", content):
        return 3, "Structural: exhaustive pattern match on status codes"

    # Score 2: validated — uses .get() with a fallback exception type
    if re.search(r"_STATUS_TO_EXCEPTION\.get\(", body):
        return 2, "Validated: .get() with fallback for unmapped codes"

    # Score 1: convention — dict subscript but mapping is documented as complete
    if re.search(r"_STATUS_TO_EXCEPTION\[", body):
        # Check if there's at least a comment or docstring about completeness
        if re.search(r"#.*all.*status|#.*exhaustive|#.*complete", content, re.IGNORECASE):
            return 1, "Convention: dict subscript with completeness comment"
        return 1, "Convention: dict subscript covers current codes but no safety net"

    return 0, "Unguarded: no status code mapping found"


def check_04_type_prefix_collision_detection() -> tuple[int, str]:
    """__init_subclass__ must detect type_prefix collisions."""
    content = (SRC / "_object.py").read_text()

    # Extract __init_subclass__ method
    match = re.search(
        r"def\s+__init_subclass__\(.*?\).*?(?=\n    def\s|\n    @|\nclass\s|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return 0, "__init_subclass__ not found"

    body = match.group()

    # Score 3: structural — type system prevents collision (e.g., unique enum, frozen registry)
    if re.search(r"UniqueRegistry|frozenset|__init_subclass_with_meta__|Final\[", body):
        return 3, "Structural: type-level uniqueness enforcement"

    # Score 2: validated — explicit collision check with error
    if re.search(
        r"if\s+type_prefix\s+in\s+.*_prefix_to_type|"
        r"raise.*collision|raise.*duplicate|raise.*already\s+registered|"
        r"assert\s+type_prefix\s+not\s+in",
        body,
        re.IGNORECASE,
    ):
        return 2, "Validated: collision check raises on duplicate prefix"

    # Score 1: convention — comment warns about uniqueness
    if re.search(r"#.*unique|#.*collision|#.*duplicate", body, re.IGNORECASE):
        return 1, "Convention: documented but not enforced"

    # Score 0: direct dict assignment with no check
    if re.search(r"_prefix_to_type\[.*\]\s*=", body):
        return 0, "Unguarded: direct dict assignment, second class silently overwrites first"

    return 0, "Unguarded: no collision detection found"


def check_05_lazy_rehydration_atomicity() -> tuple[int, str]:
    """Lazy rehydration in hydrate() must be atomic or protected by a lock."""
    content = (SRC / "_object.py").read_text()

    # Extract hydrate method
    match = re.search(
        r"async\s+def\s+hydrate\(.*?\).*?(?=\n    async\s+def\s|\n    def\s|\n    @|\nclass\s|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return 0, "hydrate() method not found"

    body = match.group()

    # Score 3: structural — uses asyncio.Lock or atomic flag pattern
    if re.search(r"asyncio\.Lock|_hydration_lock|async\s+with\s+self\._lock", body):
        return 3, "Structural: lock protects hydration state transition"

    # Score 2: validated — check-and-set pattern with flag, or compare-and-swap
    if re.search(r"_is_hydrating|_hydration_in_progress|asyncio\.Event", body):
        return 2, "Validated: hydration-in-progress flag prevents concurrent access"

    # Score 1: convention — comment acknowledges the race
    if re.search(r"#.*concurrent|#.*race|#.*thread.safe|#.*lock", body, re.IGNORECASE):
        return 1, "Convention: race condition documented but not mitigated"

    # Score 0: sets _is_hydrated = False then awaits without protection
    if re.search(r"_is_hydrated\s*=\s*False", body):
        return 0, "Unguarded: sets _is_hydrated=False then awaits without lock"

    return 0, "Unguarded: no atomicity protection found"


def check_06_volume_path_validation() -> tuple[int, str]:
    """Volume read/list operations must validate paths at the client boundary."""
    content = (SRC / "volume.py").read_text()

    # Focus on read_file, listdir, remove_file — the methods that take a path: str
    # and pass it to the server. Upload methods (put_file) use PurePosixPath for
    # formatting, but read methods may not validate at all.
    read_methods = []
    for method_name in ("read_file", "listdir", "remove_file", "read_file_into_fileobj"):
        match = re.search(
            rf"async\s+def\s+{method_name}\(.*?\).*?(?=\n    async\s+def\s|\n    def\s|\n    @(?!live)|\nclass\s|\Z)",
            content,
            re.DOTALL,
        )
        if match:
            read_methods.append((method_name, match.group()))

    if not read_methods:
        return 0, "No read/list methods found"

    # Score 3: structural — path parameter typed as a validated path type (not str)
    all_typed = all(
        re.search(r"path\s*:\s*(VolumePath|ValidatedPath)", body)
        for _, body in read_methods
    )
    if all_typed:
        return 3, "Structural: path parameter uses validated type"

    # Score 2: validated — explicit path validation in method body
    validated_count = 0
    for name, body in read_methods:
        if re.search(
            r"os\.path\.normpath|PurePosixPath\(path\)|validate_path|_check_path|"
            r"if\s+[\"']\.\.[\"']\s+in\s+path|path\.startswith",
            body,
        ):
            validated_count += 1

    if validated_count == len(read_methods):
        return 2, "Validated: all read/list methods validate paths"

    # Score 1: some methods validate or docstring mentions requirements
    if validated_count > 0:
        return 1, f"Convention: {validated_count}/{len(read_methods)} read methods validate paths"

    # Score 0: path passed directly to proto
    return 0, f"Unguarded: {len(read_methods)} read/list methods pass path directly to proto"


def check_07_deserialization_version_detection() -> tuple[int, str]:
    """Deserialization version mismatch must be detected structurally, not by string matching."""
    content = (SRC / "_serialization.py").read_text()

    # Score 3: structural — explicit version field in pickle stream or header
    if re.search(
        r"SERIALIZATION_VERSION|version_header|protocol_version.*=.*struct\.pack|"
        r"magic_bytes|FORMAT_VERSION",
        content,
    ):
        return 3, "Structural: explicit version field in serialized data"

    # Score 2: validated — uses exception attributes (exc.name, exc.obj) not string matching
    # Python 3.10+ AttributeError has .name attribute for structural detection
    if re.search(r"exc\.name\s*==|getattr\(exc,\s*['\"]name['\"]\)", content):
        return 2, "Validated: checks exception attribute (exc.name) for version detection"

    # Score 1: convention — catches exception but uses string matching on message
    # The pattern "string" in str(exc) is fragile — message could change
    if re.search(r"in\s+str\(exc\)|in\s+str\(e\)|in\s+repr\(exc\)", content):
        return 1, "Convention: fragile string matching on error message for version detection"

    return 0, "Unguarded: no version mismatch detection found"


def check_08_client_post_close_guard() -> tuple[int, str]:
    """All Client public methods must check _closed flag before executing."""
    content = (SRC / "client.py").read_text()

    # Find all public async methods on _Client
    tree = ast.parse(content)
    client_class = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "_Client":
            client_class = node
            break

    if not client_class:
        return 0, "_Client class not found"

    public_methods = []
    guarded_methods = []

    for item in client_class.body:
        if isinstance(item, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if not item.name.startswith("_") or item.name in ("__aenter__", "__aexit__"):
                continue
            # Skip private helper methods that aren't called directly
            if item.name in ("_open", "_close", "__init__", "__aenter__", "__aexit__",
                             "_new", "_from_env", "from_env", "is_closed", "__repr__"):
                continue
            public_methods.append(item.name)

            # Check if method body references is_closed or _closed
            method_src = ast.get_source_segment(content, item)
            if method_src and re.search(r"is_closed|_closed|ClientClosed", method_src):
                guarded_methods.append(item.name)

    if not public_methods:
        return 2, "Validated: no unguarded public methods found"

    ratio = len(guarded_methods) / len(public_methods) if public_methods else 0

    # Score 3: structural — decorator or metaclass enforces the check
    if re.search(r"@closed_guard|@require_open|_check_closed.*decorator", content):
        return 3, "Structural: decorator enforces closed check on all methods"

    # Score 2: all public methods check
    if ratio >= 0.8:
        return (
            2,
            f"Validated: {len(guarded_methods)}/{len(public_methods)} methods check closed flag",
        )

    # Score 1: some methods check
    if ratio >= 0.3:
        return (
            1,
            f"Convention: only {len(guarded_methods)}/{len(public_methods)} methods check closed flag",
        )

    return (
        0,
        f"Unguarded: {len(guarded_methods)}/{len(public_methods)} methods check closed flag",
    )


def check_09_unhydrate_flag_consistency() -> tuple[int, str]:
    """_unhydrate() must reset all hydration-related flags consistently."""
    content = (SRC / "_object.py").read_text()

    # Extract _unhydrate method
    match = re.search(
        r"def\s+_unhydrate\(self\).*?(?=\n    def\s|\n    @|\nclass\s|\Z)",
        content,
        re.DOTALL,
    )
    if not match:
        return 0, "_unhydrate not found"

    body = match.group()

    # Score 3: structural — state is an enum, setting it resets all derived flags
    if re.search(r"self\._state\s*=|HydrationState\.", body):
        return 3, "Structural: single state enum controls all flags"

    # Score 2: validated — resets both _is_hydrated and _is_rehydrated
    resets_hydrated = re.search(r"_is_hydrated\s*=\s*False", body)
    resets_rehydrated = re.search(r"_is_rehydrated\s*=\s*False", body)
    if resets_hydrated and resets_rehydrated:
        return 2, "Validated: resets both _is_hydrated and _is_rehydrated"

    # Score 1: resets _is_hydrated only (partial)
    if resets_hydrated and not resets_rehydrated:
        return 1, "Convention: resets _is_hydrated but not _is_rehydrated — stale flag remains"

    return 0, "Unguarded: _unhydrate doesn't reset hydration flags"


def check_10_pickle_protocol_version_tracking() -> tuple[int, str]:
    """Serialized data must include protocol version for safe deserialization."""
    content = (SRC / "_serialization.py").read_text()

    # Score 3: structural — version header in serialized bytes
    if re.search(
        r"struct\.pack.*version|version_bytes|MAGIC.*version|header.*protocol",
        content,
        re.IGNORECASE,
    ):
        return 3, "Structural: version header embedded in serialized data"

    # Score 2: validated — version checked before deserialization
    if re.search(
        r"check_protocol_version|if.*PICKLE_PROTOCOL.*!=|version.*mismatch.*raise",
        content,
        re.IGNORECASE,
    ):
        return 2, "Validated: protocol version checked before deserializing"

    # Score 1: convention — protocol version defined as constant but not transmitted
    if re.search(r"PICKLE_PROTOCOL\s*=\s*\d+", content):
        # Check if it's used in both serialization and deserialization
        pickler_uses = len(re.findall(r"protocol\s*=\s*PICKLE_PROTOCOL", content))
        if pickler_uses >= 1:
            return 1, f"Convention: PICKLE_PROTOCOL={re.search(r'PICKLE_PROTOCOL = (d+)', content) and 'defined' or '4'} used in Pickler but not embedded in stream"

    return 0, "Unguarded: no protocol version tracking"


# ════════════════════════════════════════════════════════════════════
# Harness
# ════════════════════════════════════════════════════════════════════

INVARIANTS = [
    ("init_from_other_guard", check_01_initialize_from_other_hydration_guard),
    ("prefix_validation", check_02_prefix_validation_consistency),
    ("grpc_status_safety", check_03_grpc_status_mapping_safety),
    ("prefix_collision", check_04_type_prefix_collision_detection),
    ("rehydration_atomicity", check_05_lazy_rehydration_atomicity),
    ("volume_path_validation", check_06_volume_path_validation),
    ("deser_version_detect", check_07_deserialization_version_detection),
    ("client_close_guard", check_08_client_post_close_guard),
    ("unhydrate_flag_consistency", check_09_unhydrate_flag_consistency),
    ("pickle_version_tracking", check_10_pickle_protocol_version_tracking),
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
