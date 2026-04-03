# Formalization Findings

## Discovered Invariants

### 1. Hydration state ↔ object_id availability
**Discovery:** Defining `ModalObject` with `objectId : Option String` forced explicit handling of the None case. In Python, `_object_id: Optional[str]` is typed as optional but treated as required after hydration. The `.object_id` property guards with AttributeError, but `_object_id` (the raw field) is accessed directly in `_initialize_from_other` (line 157), which copies None without checking.
**Current enforcement:** validated (the property guards, but the underlying field is unguarded)
**Lean evidence:** `objectId_iff_hydrated` theorem — can't prove without a state invariant that Python doesn't enforce
**Risk:** `_initialize_from_other` called on an unhydrated source silently copies `None` as the object_id. Downstream gRPC calls send `function_id=None`, which produces a confusing server error instead of a clear "unhydrated object" error.

### 2. Prefix validation inconsistency between _hydrate and _new_hydrated
**Discovery:** Writing `validateHydrate` and `validateNewHydrated` as separate functions made the difference visible: `startsWith(prefix)` vs `startsWith(prefix ++ "-")`. The theorem `prefix_validation_consistent` proves one direction but not the other.
**Current enforcement:** convention — both paths validate, but with different strictness
**Lean evidence:** `prefix_validation_consistent` — the weaker check in `_hydrate` accepts IDs that `_new_hydrated` rejects
**Risk:** An object_id with prefix "fnx" passes `_hydrate`'s check when type_prefix is "fn" (since "fnx-abc".startsWith("fn") is true). The object gets hydrated with a wrong type prefix. Silent type confusion.

### 3. gRPC status code mapping is non-exhaustive by construction
**Discovery:** Defining `GRPCStatus` as an inductive type and writing `statusToException` as a total function forced handling of `.ok`. The Python dict uses `[exc.status]` (subscript), not `.get()`, so any unmapped code raises `KeyError`.
**Current enforcement:** convention — the mapping covers all current codes, but nothing prevents drift
**Lean evidence:** `error_status_total` theorem proves all error codes map; `ok_not_mapped` shows the gap
**Risk:** If grpclib adds a new status code, or if a server sends an unexpected code, `KeyError` replaces the actual gRPC error. The original error message is lost.

### 4. Type prefix registry allows silent collisions
**Discovery:** Modeling `TypeRegistry` and writing `no_prefix_collision` as a theorem revealed there's no collision check in `__init_subclass__`. The second subclass silently overwrites the first.
**Current enforcement:** unguarded — no detection mechanism exists
**Lean evidence:** `no_prefix_collision` theorem — can't prove because the Python code doesn't enforce it
**Risk:** If two `_Object` subclasses register the same `_type_prefix`, `_get_type_from_id` returns the wrong class for the overwritten prefix. Deserialization creates an object of the wrong type. Silent type confusion.

### 5. Retryable status and exception type are decoupled contracts
**Discovery:** Writing `isRetryable` and trying to prove `retryable_maps_to_service_error` revealed that INTERNAL maps to `InternalError` (not `ServiceError`) but is retried. The retry logic checks the gRPC status code directly, independent of the exception mapping.
**Current enforcement:** convention — the two mappings are in different files with no shared definition
**Lean evidence:** `retryable_maps_to_service_error` theorem — intentionally unprovable, revealing the contract gap
**Risk:** A developer adding retry logic might check the Modal exception type (thinking ServiceError = retryable) instead of the gRPC status code. The abstraction leaks.

### 6. Lazy rehydration creates a transient unhydrated window
**Discovery:** Modeling `HydrateOutcome` revealed that the `rehydratedLazy` case sets `_is_hydrated = False` then re-resolves asynchronously. During this window, concurrent coroutines see an unhydrated object.
**Current enforcement:** unguarded — no lock or atomic flag protects the transition
**Lean evidence:** `ValidTransition.rehydrate_lazy` — hydrated → unhydrated transition has no corresponding "in-progress" state
**Risk:** In async code, if coroutine A triggers lazy rehydration and coroutine B accesses the object during re-resolution, B gets `AttributeError` from the `.object_id` property (or worse, if it accesses `_object_id` directly, it gets `None`).

## Lean Spec Summary
- Files: HydrationLifecycle.lean, GRPCErrorMapping.lean, ObjectIdFormat.lean, LiveMethodContract.lean
- `lake build`: pass (0 errors, 10 sorry warnings — all proofs are sorry as expected)
- sorry count: 10
