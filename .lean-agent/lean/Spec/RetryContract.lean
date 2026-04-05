namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Retry Contract — cross-language consistency
--
-- Both Go and Python implement exponential backoff retry for gRPC
-- calls. The contract: given the same error and same call options,
-- both languages should retry the same number of times with the
-- same delay progression.
-- ════════════════════════════════════════════════════════════════════

/-- Retry configuration parameters -/
structure RetryConfig where
  maxAttempts : Nat       -- Total attempts (Go: 3 default, Python: unbounded)
  baseDelay   : Nat       -- Milliseconds (both: 100ms)
  maxDelay    : Nat       -- Milliseconds (both: 1000ms)
  backoffMul  : Nat       -- Multiplier × 10 (both: 20, representing 2.0x)
  deriving Repr

/-- Go defaults -/
def goRetryDefault : RetryConfig :=
  { maxAttempts := 3
  , baseDelay := 100
  , maxDelay := 1000
  , backoffMul := 20  -- 2.0x
  }

-- ════════════════════════════════════════════════════════════════════
-- CRITICAL DIVERGENCE: Python has NO default max attempts
--
-- Go: defaultRetryAttempts = 3
-- Python: Retry dataclass has no `max_retries` field at all.
--   Retries are bounded by total timeout (context deadline), not count.
--
-- Impact: For calls without a deadline, Python retries indefinitely
-- on transient errors. Go gives up after 3 attempts.
-- This means: a server returning Unavailable will cause Python to
-- spin forever while Go fails after ~1.4 seconds.
-- ════════════════════════════════════════════════════════════════════

/-- Compute delay for attempt N (exponential backoff, capped) -/
def computeDelay (cfg : RetryConfig) (attempt : Nat) : Nat :=
  let raw := cfg.baseDelay * (cfg.backoffMul / 10) ^ attempt
  min raw cfg.maxDelay

/-- Delay sequence is monotonically non-decreasing until cap -/
theorem delay_monotone (cfg : RetryConfig) (n : Nat)
    (h_base_pos : cfg.baseDelay > 0)
    (h_mul_ge : cfg.backoffMul ≥ 10)
    : computeDelay cfg n ≤ computeDelay cfg (n + 1) ∨
      computeDelay cfg n = cfg.maxDelay := by
  sorry

-- ════════════════════════════════════════════════════════════════════
-- Retryable status codes — must agree cross-language
-- ════════════════════════════════════════════════════════════════════

/-- gRPC status codes (subset relevant to retry) -/
inductive GrpcCode where
  | ok                  : GrpcCode
  | cancelled           : GrpcCode
  | unknown             : GrpcCode
  | invalidArgument     : GrpcCode
  | deadlineExceeded    : GrpcCode
  | notFound            : GrpcCode
  | alreadyExists       : GrpcCode
  | permissionDenied    : GrpcCode
  | resourceExhausted   : GrpcCode
  | failedPrecondition  : GrpcCode
  | aborted             : GrpcCode
  | outOfRange          : GrpcCode
  | unimplemented       : GrpcCode
  | internal            : GrpcCode
  | unavailable         : GrpcCode
  | dataLoss            : GrpcCode
  | unauthenticated     : GrpcCode
  deriving DecidableEq, Repr

/-- Go's retryable set: {DeadlineExceeded, Unavailable, Cancelled, Internal, Unknown} -/
def goRetryable (code : GrpcCode) : Bool :=
  match code with
  | .deadlineExceeded => true
  | .unavailable      => true
  | .cancelled        => true
  | .internal         => true
  | .unknown          => true
  | _                 => false

-- ════════════════════════════════════════════════════════════════════
-- Discovered invariant: retry idempotency key
--
-- Go generates a UUID v4 per-call and sends it on every retry attempt
-- as x-idempotency-key. This enables server-side deduplication.
-- If Python doesn't send the same header, retried mutations
-- could be applied multiple times.
-- ════════════════════════════════════════════════════════════════════

/-- Idempotency key must be:
    1. Generated once per logical call (not per attempt)
    2. Sent on every retry attempt for that call
    3. Unique across concurrent calls -/
structure IdempotencyContract where
  key        : String
  callID     : Nat     -- Logical call identifier
  attemptNum : Nat     -- Which attempt this is
  deriving Repr

/-- Same call → same key across attempts -/
theorem idempotency_stable
    (c1 c2 : IdempotencyContract)
    (h : c1.callID = c2.callID)
    : c1.key = c2.key := by
  sorry

end Spec
