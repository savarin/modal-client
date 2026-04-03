/-
  Live Method Decorator Contract

  Models the `live_method`, `live_method_gen`, and `live_method_contextmanager`
  decorators in _object.py. These wrappers call `hydrate()` before the actual
  method, ensuring the object is ready for use.

  Key discovery targets:
  - Do all methods that access object_id use a live_method wrapper?
  - What happens if a method accesses _object_id directly without the wrapper?
  - Is there a contract between "needs hydration" and "uses live_method"?
-/

namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Method classification
-- ════════════════════════════════════════════════════════════════════

/-- Whether a method accesses server-side state (needs hydration). -/
inductive AccessKind where
  | localOnly     -- only reads local fields (name, rep, etc.)
  | needsServer   -- accesses object_id, client, or makes gRPC calls
deriving Repr, BEq

/-- Whether a method has hydration protection. -/
inductive Protection where
  | liveMethod            -- wrapped with @live_method
  | liveMethodGen         -- wrapped with @live_method_gen
  | liveMethodCtxMgr      -- wrapped with @live_method_contextmanager
  | propertyGuard          -- property with explicit None check
  | validateIsHydrated     -- calls _validate_is_hydrated
  | unprotected            -- no hydration check
deriving Repr, BEq

/-- A method on a Modal object. -/
structure ModalMethod where
  name : String
  accessKind : AccessKind
  protection : Protection
deriving Repr

-- ════════════════════════════════════════════════════════════════════
-- Invariants
-- ════════════════════════════════════════════════════════════════════

/-- INVARIANT 1: All methods that need server access must be protected.
    DISCOVERY: In the codebase, most public methods use @live_method.
    But some methods access self._object_id directly (e.g., _initialize_from_other
    at line 157: `self._object_id = other._object_id`). This bypasses the
    property guard and copies None if `other` is not hydrated.

    The `object_id` property (line 307-310) is protected.
    But `_object_id` (the underlying field) is not.
    Any code that reads `self._object_id` directly gets None without warning.
-/
theorem server_methods_protected (m : ModalMethod) :
    m.accessKind = .needsServer →
    m.protection ≠ .unprotected := by
  sorry

/-- INVARIANT 2: _initialize_from_other should only be called with hydrated sources.
    In Python (line 155-159):
    ```
    def _initialize_from_other(self, other):
        self._object_id = other._object_id  -- copies None if other is unhydrated!
        self._is_hydrated = other._is_hydrated
        self._client = other._client
    ```
    No check that `other` is hydrated. The caller (clone at line 211) does check,
    but _initialize_from_other itself is unguarded.
-/
def initializeFromOtherSafe (sourceHydrated : Bool) : Bool :=
  sourceHydrated  -- Only safe if source is hydrated

theorem initialize_requires_hydrated_source :
    ∀ (hydrated : Bool), initializeFromOtherSafe hydrated = true → hydrated = true := by
  intro h hp
  exact hp

/-- INVARIANT 3: The hydrate() method handles 3 distinct cases:
    1. Already hydrated + snapshotted + not rehydrated → rehydrate
    2. Not hydrated + not lazy → validate (raises error)
    3. Not hydrated + lazy → resolve via loader

    DISCOVERY: Case 1 has a sub-branch: if _hydrate_lazily, it sets
    _is_hydrated = False then re-resolves. During re-resolution, the object
    is in a transient unhydrated state. If another coroutine accesses the
    object during this window, it gets an unhydrated object.
    This is a concurrency hazard — no lock protects the transition.
-/
inductive HydrateOutcome where
  | alreadyHydrated
  | rehydratedEager    -- snapshotted, non-lazy: just replaces client
  | rehydratedLazy     -- snapshotted, lazy: un-hydrates then re-resolves
  | validationError    -- not hydrated, not lazy: raises ExecutionError
  | lazyResolution     -- not hydrated, lazy: resolves via loader
deriving Repr

end Spec
