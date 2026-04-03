/-
  Modal Object Hydration Lifecycle

  Models the state machine in _object.py. Objects are created unhydrated
  (with `_from_loader`), then hydrated (via `_hydrate` or `hydrate`),
  and optionally rehydrated after a snapshot restore.

  Key discovery targets:
  - Is `_object_id` always available when the object is used?
  - Can an object transition back to unhydrated after hydration?
  - What operations are valid in each state?
-/

namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Core types
-- ════════════════════════════════════════════════════════════════════

/-- Object ID: always "prefix-uuid" format when present. -/
structure ObjectId where
  pfx : String
  uid : String
deriving Repr

/-- A type prefix registered by a subclass. -/
structure TypePrefix where
  val : String
deriving Repr

/-- Hydration state machine.
    In the Python code:
    - UNHYDRATED: `_object_id = None`, `_client = None`, `_is_hydrated = False`
    - HYDRATED: `_object_id = Some id`, `_client = Some c`, `_is_hydrated = True`
    - REHYDRATED: same as HYDRATED but `_is_rehydrated = True`
    - DEHYDRATED: after `_unhydrate()`, returns to `_object_id = None`
-/
inductive HydrationState where
  | unhydrated
  | hydrated
  | rehydrated
  | dehydrated
deriving Repr, BEq

/-- An object in the Modal system.
    Note: `objectId` is only `some` when `state` is `hydrated` or `rehydrated`.
    This is the key invariant — in Python, `_object_id: Optional[str]` is accessed
    as if it were `str` in many places.
-/
structure ModalObject where
  state : HydrationState
  objectId : Option String  -- simplified to String for Repr
  typePrefix : Option String
  hasLoad : Bool
  hydrateLazily : Bool
deriving Repr

-- ════════════════════════════════════════════════════════════════════
-- State machine transitions
-- ════════════════════════════════════════════════════════════════════

/-- Valid transitions for the hydration state machine. -/
inductive ValidTransition : HydrationState → HydrationState → Prop where
  | hydrate : ValidTransition .unhydrated .hydrated
  | rehydrate : ValidTransition .hydrated .rehydrated
  | dehydrate_from_hydrated : ValidTransition .hydrated .dehydrated
  | dehydrate_from_rehydrated : ValidTransition .rehydrated .dehydrated
  -- DISCOVERY: _unhydrate sets _is_hydrated = False but doesn't set _is_rehydrated = False
  -- So a dehydrated object could still have _is_rehydrated = True from a prior snapshot.
  | rehydrate_lazy : ValidTransition .hydrated .unhydrated
  -- In hydrate(), when _snapshotted and _hydrate_lazily: sets _is_hydrated = False
  -- then re-resolves. This transitions hydrated → unhydrated → hydrated.

-- ════════════════════════════════════════════════════════════════════
-- Invariants as theorems
-- ════════════════════════════════════════════════════════════════════

/-- INVARIANT 1: objectId is Some iff state is hydrated or rehydrated.
    In Python: `_object_id` is set in `_hydrate()` and cleared in `_unhydrate()`.
    The `.object_id` property raises AttributeError if None.
    BUT: code that accesses `self._object_id` directly bypasses this check.
-/
theorem objectId_iff_hydrated (obj : ModalObject) :
    obj.objectId.isSome = true ↔
    (obj.state = .hydrated ∨ obj.state = .rehydrated) := by
  sorry

/-- INVARIANT 2: If state is unhydrated, objectId must be None.
    Violated if _unhydrate() is called but some code cached the object_id.
-/
theorem unhydrated_no_id (obj : ModalObject) :
    obj.state = .unhydrated → obj.objectId = none := by
  sorry

/-- INVARIANT 3: After dehydration, objectId must be None.
    _unhydrate() sets _object_id = None. But does anything cache it?
    DISCOVERY: _hydrate_from_other (line 295-296) accesses other.object_id
    which goes through the property. But _initialize_from_other (line 156-159)
    copies _object_id directly — no hydration check.
-/
theorem dehydrated_no_id (obj : ModalObject) :
    obj.state = .dehydrated → obj.objectId = none := by
  sorry

/-- INVARIANT 4: Lazy hydration requires a load callback.
    If hydrateLazily is true but hasLoad is false, hydrate() will fail
    silently — it enters the lazy branch but has nothing to call.
    In Python: the else branch at line 370-377 calls resolver.load(self, ...)
    which invokes self._load. If _load is None... what happens?
-/
theorem lazy_requires_load (obj : ModalObject) :
    obj.hydrateLazily = true → obj.hasLoad = true := by
  sorry

end Spec
