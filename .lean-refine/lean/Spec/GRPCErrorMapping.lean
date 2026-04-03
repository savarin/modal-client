/-
  gRPC Error Status Code → Modal Exception Mapping

  Models the contract between _grpc_client.py and exception.py.
  The _STATUS_TO_EXCEPTION dict maps grpclib.Status codes to Modal exception types.

  Key discovery targets:
  - Is the mapping total (covers all possible status codes)?
  - What happens when a status code is not in the mapping?
  - Is there a contract between the docstring in exception.py and the actual dict?
-/

namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- gRPC status codes (from grpclib.Status enum)
-- ════════════════════════════════════════════════════════════════════

/-- All gRPC status codes as defined in the gRPC spec.
    grpclib.Status has 17 members (OK + 16 error codes).
-/
inductive GRPCStatus where
  | ok
  | cancelled
  | unknown
  | invalidArgument
  | deadlineExceeded
  | notFound
  | alreadyExists
  | permissionDenied
  | resourceExhausted
  | failedPrecondition
  | aborted
  | outOfRange
  | unimplemented
  | internal
  | unavailable
  | dataLoss
  | unauthenticated
deriving Repr, BEq, DecidableEq

/-- Modal exception types that map from gRPC errors. -/
inductive ModalException where
  | serviceError
  | invalidError
  | notFoundError
  | alreadyExistsError
  | permissionDeniedError
  | resourceExhaustedError
  | conflictError
  | unimplementedError
  | internalError
  | dataLossError
  | authError
deriving Repr, BEq

-- ════════════════════════════════════════════════════════════════════
-- The mapping function
-- ════════════════════════════════════════════════════════════════════

/-- The mapping from _STATUS_TO_EXCEPTION in _grpc_client.py.
    DISCOVERY: This is a partial function in Python (dict subscript, not .get()).
    The `ok` status is NOT in the dict. If a GRPCError with status OK is caught
    by grpc_error_converter, it will raise KeyError, not a Modal exception.

    Making this a total function forces us to handle every case.
-/
def statusToException (s : GRPCStatus) : Option ModalException :=
  match s with
  | .ok => none  -- NOT MAPPED in Python → KeyError at runtime
  | .cancelled => some .serviceError
  | .unknown => some .serviceError
  | .invalidArgument => some .invalidError
  | .deadlineExceeded => some .serviceError
  | .notFound => some .notFoundError
  | .alreadyExists => some .alreadyExistsError
  | .permissionDenied => some .permissionDeniedError
  | .resourceExhausted => some .resourceExhaustedError
  | .failedPrecondition => some .conflictError
  | .aborted => some .conflictError
  | .outOfRange => some .invalidError
  | .unimplemented => some .unimplementedError
  | .internal => some .internalError
  | .unavailable => some .serviceError
  | .dataLoss => some .dataLossError
  | .unauthenticated => some .authError

-- ════════════════════════════════════════════════════════════════════
-- Invariants
-- ════════════════════════════════════════════════════════════════════

/-- INVARIANT 1: All error status codes (non-OK) must map to a Modal exception.
    In Python: _STATUS_TO_EXCEPTION[exc.status] uses dict subscript.
    If any error code is missing, we get KeyError instead of the proper Modal exception.
    DISCOVERY: Currently all 16 error codes are mapped. But this is convention (1),
    not structural — nothing prevents adding a new grpclib.Status value without
    updating the dict.
-/
theorem error_status_total (s : GRPCStatus) :
    s ≠ .ok → (statusToException s).isSome = true := by
  intro h
  cases s <;> simp [statusToException] <;> try contradiction

/-- INVARIANT 2: OK status should never reach the error converter.
    In Python: grpc_error_converter only triggers on GRPCError exceptions.
    A successful RPC returns normally, not via exception. But if a server
    incorrectly raises GRPCError with status OK...
-/
theorem ok_not_mapped :
    statusToException .ok = none := by
  rfl

/-- Retryable statuses — the retry logic in grpc_utils.py treats some errors as transient.
    DISCOVERY: Is the set of retryable statuses consistent with the exception mapping?
    ServiceError is the catch-all for retryable errors. Do all retryable statuses
    map to ServiceError? Let's check.
-/
def isRetryable (s : GRPCStatus) : Bool :=
  match s with
  | .unavailable => true
  | .deadlineExceeded => true
  | .cancelled => true
  | .internal => true    -- DISCOVERY: internal maps to InternalError, not ServiceError
  | .unknown => true     -- maps to ServiceError
  | _ => false

/-- INVARIANT 3: Retryable statuses should map to a consistent exception type.
    DISCOVERY: This doesn't hold. INTERNAL maps to InternalError but is retryable.
    The retry logic checks the gRPC status code directly, not the Modal exception type.
    This means the "retry-ability" and the "exception type" are independent contracts
    that could diverge silently.
-/
theorem retryable_maps_to_service_error (s : GRPCStatus) :
    isRetryable s = true →
    statusToException s = some .serviceError := by
  sorry  -- This SHOULD fail — internal maps to internalError, not serviceError.
         -- The retry decision and exception type are decoupled contracts.

end Spec
