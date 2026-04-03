/-
  Object ID Format and Type Prefix Registry

  Models the object_id format contract ("prefix-uuid") and the
  type_prefix → class registry in _object.py.

  Key discovery targets:
  - Is prefix validation consistent across all entry points?
  - Can two classes register the same type_prefix?
  - What happens with malformed object IDs?
-/

namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Object ID parsing
-- ════════════════════════════════════════════════════════════════════

/-- Parse result — either a valid parsed ID or an error. -/
inductive ParseResult where
  | ok (pfx : String) (uid : String)
  | noDash
  | multipleDashes
  | emptyPrefix
  | emptyUuid
deriving Repr

-- ════════════════════════════════════════════════════════════════════
-- Type prefix registry
-- ════════════════════════════════════════════════════════════════════

/-- The registry mapping prefixes to types.
    In Python: `_prefix_to_type: ClassVar[dict[str, type]] = {}`
    Populated by `__init_subclass__`.
-/
structure TypeRegistry where
  entries : List (String × String)
deriving Repr

/-- Check if a prefix is registered. -/
def TypeRegistry.hasPrefix (reg : TypeRegistry) (pfx : String) : Bool :=
  reg.entries.any (fun e => e.1 == pfx)

-- ════════════════════════════════════════════════════════════════════
-- Prefix validation functions (as they exist in the Python code)
-- ════════════════════════════════════════════════════════════════════

/-- Validation in `_hydrate` (line 162-163):
    `if not object_id.startswith(self._type_prefix):`
    Note: checks `startsWith(prefix)`, NOT `startsWith(prefix ++ "-")`
-/
def validateHydrate (objectId : String) (typePrefix : String) : Bool :=
  objectId.startsWith typePrefix

/-- Validation in `_new_hydrated` (line 278):
    `if not object_id.startswith(cls._type_prefix + "-"):`
    Note: checks `startsWith(prefix ++ "-")` — stricter than _hydrate!
-/
def validateNewHydrated (objectId : String) (typePrefix : String) : Bool :=
  objectId.startsWith (typePrefix ++ "-")

-- ════════════════════════════════════════════════════════════════════
-- Invariants
-- ════════════════════════════════════════════════════════════════════

/-- INVARIANT 1: Prefix validation must be consistent.
    DISCOVERY: _hydrate checks `startsWith(prefix)` while _new_hydrated
    checks `startsWith(prefix ++ "-")`. This means:
    - _hydrate("fn", "fn-abc") → OK (correct)
    - _hydrate("fn", "fnx-abc") → OK (BUG: "fnx" prefix matches "fn")
    - _new_hydrated("fn", "fnx-abc") → FAIL (correct)

    An object_id with prefix "fnx" would pass _hydrate's check when the
    type_prefix is "fn" but fail _new_hydrated's check.
-/
theorem prefix_validation_consistent (objectId typePrefix : String) :
    validateNewHydrated objectId typePrefix = true →
    validateHydrate objectId typePrefix = true := by
  sorry

/-- INVARIANT 2: Type prefix registry has no collisions.
    In Python: __init_subclass__ does `cls._prefix_to_type[type_prefix] = cls`
    with no collision check. If two subclasses use the same prefix, the second
    silently overwrites the first.
-/
theorem no_prefix_collision (reg : TypeRegistry) :
    ∀ (i j : Fin reg.entries.length),
      i ≠ j →
      (reg.entries.get i).1 ≠ (reg.entries.get j).1 := by
  sorry

/-- INVARIANT 3: _get_type_from_id requires exactly one dash.
    Object IDs with multiple dashes would fail.
    DISCOVERY: Modal uses its own ID format (prefix-hexstring), not raw UUIDs.
    But the split-on-dash approach is fragile if the format ever changes.
-/
theorem get_type_single_dash (objectId : String) :
    (objectId.splitOn "-").length = 2 →
    ∃ (pfx uuid : String), objectId = pfx ++ "-" ++ uuid := by
  sorry

end Spec
