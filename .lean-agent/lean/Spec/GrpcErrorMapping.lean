import Spec.RetryContract

namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- gRPC Error → Exception Mapping — cross-language contract
--
-- Python maps gRPC status codes to Modal exception types.
-- Go uses gRPC status codes directly (no custom exception hierarchy).
-- The contract: both languages must handle the same error from the
-- server in a semantically equivalent way.
-- ════════════════════════════════════════════════════════════════════

/-- Modal exception types (Python side) -/
inductive ModalException where
  | notFound          : ModalException
  | alreadyExists     : ModalException
  | invalid           : ModalException  -- InvalidArgument OR OutOfRange
  | permissionDenied  : ModalException
  | conflict          : ModalException  -- FailedPrecondition OR Aborted
  | resourceExhausted : ModalException
  | unimplemented     : ModalException
  | internal          : ModalException
  | dataLoss          : ModalException
  | auth              : ModalException  -- Unauthenticated
  | service           : ModalException  -- Cancelled, Unknown, DeadlineExceeded, Unavailable
  deriving DecidableEq, Repr

-- Re-use GrpcCode from RetryContract
open GrpcCode in

/-- Python's gRPC → Modal exception mapping.
    This is the source of truth from _grpc_client.py -/
def pythonExceptionMapping (code : GrpcCode) : Option ModalException :=
  match code with
  | .ok                 => none  -- not an error
  | .notFound           => some .notFound
  | .alreadyExists      => some .alreadyExists
  | .invalidArgument    => some .invalid
  | .outOfRange         => some .invalid      -- maps to same as invalidArgument
  | .permissionDenied   => some .permissionDenied
  | .failedPrecondition => some .conflict
  | .aborted            => some .conflict     -- maps to same as failedPrecondition
  | .resourceExhausted  => some .resourceExhausted
  | .unimplemented      => some .unimplemented
  | .internal           => some .internal
  | .dataLoss           => some .dataLoss
  | .unauthenticated    => some .auth
  | .cancelled          => some .service
  | .unknown            => some .service
  | .deadlineExceeded   => some .service
  | .unavailable        => some .service

-- ════════════════════════════════════════════════════════════════════
-- Exhaustiveness theorem
--
-- Every gRPC status code must map to exactly one Modal exception.
-- This IS structurally enforced in Python via exhaustive match.
-- ════════════════════════════════════════════════════════════════════

theorem mapping_exhaustive (code : GrpcCode) (h : code ≠ .ok)
    : (pythonExceptionMapping code).isSome = true := by
  sorry

-- ════════════════════════════════════════════════════════════════════
-- Discovered invariant: Go has NO equivalent mapping
--
-- Go returns raw gRPC status.Error to callers. The Go SDK user
-- must match on codes.Code themselves. This means:
--
-- 1. Python users catch `InvalidError` — Go users check `codes.InvalidArgument`
-- 2. Python merges InvalidArgument + OutOfRange → InvalidError
--    Go users must check BOTH codes to get equivalent behavior
-- 3. Python merges FailedPrecondition + Aborted → ConflictError
--    Go users must check BOTH codes
--
-- A Go user who only checks codes.InvalidArgument will miss
-- OutOfRange errors that Python would catch as InvalidError.
-- This is convention-level at best — there's no way to enforce
-- that Go callers check the right set of codes.
-- ════════════════════════════════════════════════════════════════════

/-- Codes that Python merges under InvalidError -/
def invalidGroup : List GrpcCode := [.invalidArgument, .outOfRange]

/-- Codes that Python merges under ConflictError -/
def conflictGroup : List GrpcCode := [.failedPrecondition, .aborted]

/-- Codes that Python merges under ServiceError -/
def serviceGroup : List GrpcCode := [.cancelled, .unknown, .deadlineExceeded, .unavailable]

-- ════════════════════════════════════════════════════════════════════
-- Retry × Error interaction
--
-- Go retries: {DeadlineExceeded, Unavailable, Cancelled, Internal, Unknown}
-- Python service group: {Cancelled, Unknown, DeadlineExceeded, Unavailable}
--
-- Note: Go retries Internal, but Python maps Internal → InternalError
-- (not ServiceError). This means Python does NOT auto-retry Internal
-- errors the same way. Cross-language semantic divergence.
-- ════════════════════════════════════════════════════════════════════

/-- Go retries Internal; Python does not treat it as a transient service error -/
theorem internal_retry_divergence :
    goRetryable .internal = true ∧
    pythonExceptionMapping .internal = some .internal := by
  sorry

end Spec
