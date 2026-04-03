# Improvement Targets

Baseline IES: 0.1667 (5/30)
Theoretical max IES: 1.00

## Theoretical maximum table

| Check function | Max returnable score | What triggers score 3 |
|---|---|---|
| check_01_initialize_from_other_hydration_guard | 3 | `HydratedObject` NewType or dataclass wrapper around object_id |
| check_02_prefix_validation_consistency | 3 | `_validate_prefix` shared function detected in source |
| check_03_grpc_status_mapping_safety | 3 | `match exc.status` exhaustive pattern match |
| check_04_type_prefix_collision_detection | 3 | `UniqueRegistry` or `Final` or frozen registry type |
| check_05_lazy_rehydration_atomicity | 3 | `asyncio.Lock` or `_hydration_lock` in hydrate() |
| check_06_volume_path_validation | 3 | `path: VolumePath` or `ValidatedPath` typed parameter |
| check_07_deserialization_version_detection | 3 | `SERIALIZATION_VERSION` or `FORMAT_VERSION` header in stream |
| check_08_client_post_close_guard | 3 | `@closed_guard` decorator on all methods |
| check_09_unhydrate_flag_consistency | 3 | Single `HydrationState` enum instead of boolean flags |
| check_10_pickle_protocol_version_tracking | 3 | `struct.pack` version header in serialized bytes |

## Strategic assessment

This repo's risk concentrates at the **object lifecycle boundary** — the hydration state machine, prefix validation, and flag management are all in `_object.py` and affect every Modal resource type. The hidden-invariant density is high in `_object.py` and `_grpc_client.py` because the abstractions are deeply trusted by downstream code (functions, volumes, images) that never check whether the foundation is sound. The cheapest wins are in `_object.py` (3 invariants scorable with small changes) and `_grpc_client.py` (1 invariant, ~3 lines).

## Phase 1 targets (execute sequentially)

### Target 1: grpc_status_safety (1→2)
**Invariant:** gRPC error converter must handle unmapped status codes without KeyError
**Category:** input validation
**Strategy:** validated
**Where:** `grep -n '_STATUS_TO_EXCEPTION\[' py/modal/_grpc_client.py`
**What:** Change `_STATUS_TO_EXCEPTION[exc.status]` to `_STATUS_TO_EXCEPTION.get(exc.status, WrappedGRPCError)` with a fallback
**Test:** No new test needed — this is a safety net for an edge case

### Target 2: unhydrate_flag_consistency (1→2)
**Invariant:** `_unhydrate()` must reset both `_is_hydrated` and `_is_rehydrated`
**Category:** state machine
**Strategy:** validated
**Where:** `grep -n '_unhydrate' py/modal/_object.py`
**What:** Add `self._is_rehydrated = False` to `_unhydrate()`
**Test:** Existing tests should pass; this prevents stale state after dehydration

### Target 3: prefix_validation (1→2)
**Invariant:** `_hydrate` and `_new_hydrated` must use the same prefix validation pattern
**Category:** contract consistency
**Strategy:** validated
**Where:** `grep -n 'startswith.*_type_prefix' py/modal/_object.py`
**What:** Change `_hydrate` to use `startswith(self._type_prefix + "-")` matching `_new_hydrated`
**Test:** Existing tests; add assertion comment explaining the pattern

### Target 4: init_from_other_guard (0→2)
**Invariant:** `_initialize_from_other` must validate source is hydrated before copying
**Category:** type safety
**Strategy:** validated
**Where:** `grep -n '_initialize_from_other' py/modal/_object.py`
**What:** Use `other.object_id` (property with guard) instead of `other._object_id`
**Test:** Existing tests should pass; unhydrated source now raises AttributeError

### Target 5: prefix_collision (0→2)
**Invariant:** `__init_subclass__` must detect duplicate type_prefix registration
**Category:** scope / isolation
**Strategy:** validated
**Where:** `grep -n '__init_subclass__' py/modal/_object.py`
**What:** Add `if type_prefix in cls._prefix_to_type: raise InvalidError(...)`
**Test:** Write a test that registers two classes with the same prefix

### Target 6: deser_version_detect (1→2)
**Invariant:** Deserialization version mismatch should use exception attributes, not string matching
**Category:** encoding / serialization
**Strategy:** validated
**Where:** `grep -n '_make_function' py/modal/_serialization.py`
**What:** Change `"Can't get attribute '_make_function'" in str(exc)` to `getattr(exc, 'name', None) == '_make_function'`
**Test:** Existing tests; the new pattern is equivalent but more robust

### Target 7: client_close_guard (0→2)
**Invariant:** All Client methods that use the connection must check `_closed`
**Category:** resource management
**Strategy:** validated
**Where:** `grep -n 'async def _' py/modal/client.py`
**What:** Add `if self.is_closed(): raise ClientClosed(id(self))` to key methods, or add it to the gRPC call path
**Test:** Write a test that calls a method after client close

### Target 8: prefix_validation (2→3) — structural attempt
**Invariant:** Prefix validation consistency enforced at the type level
**Category:** contract consistency
**Strategy:** structural
**Where:** `grep -n 'startswith.*_type_prefix' py/modal/_object.py`
**What:** Extract a `_validate_prefix(object_id, type_prefix)` function used by both methods. If >30 lines, fall back to target 3's validated approach.
**Test:** Existing tests

### Target 9: volume_path_validation (0→2)
**Invariant:** Volume read/list operations must validate paths before sending to server
**Category:** input validation (boundary)
**Strategy:** validated
**Where:** `grep -n 'async def read_file\|async def listdir\|async def remove_file' py/modal/volume.py`
**What:** Add basic path normalization (reject empty, strip leading/trailing whitespace)
**Test:** Write a test with edge case paths

### Target 10: rehydration_atomicity (0→1)
**Invariant:** Lazy rehydration race condition should be documented
**Category:** concurrency
**Strategy:** convention (lock would be >30 lines and architecturally complex)
**Where:** `grep -n '_is_hydrated.*False' py/modal/_object.py`
**What:** Add comment documenting the race condition and why a lock isn't used
**Test:** N/A — documentation only

## Phase 2 ideas (explore after Phase 1)
- Promote unhydrate_flag_consistency to structural (3) via HydrationState enum
- Promote prefix_collision to structural (3) via frozen registry with UniqueDict
- Add SERIALIZATION_VERSION header to pickle stream (pickle_version_tracking 1→3)
- Promote init_from_other_guard to structural (3) via HydratedObject wrapper type
- Explore whether _call_unary's closed check (client_close_guard) covers all paths
