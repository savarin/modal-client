namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Sandbox Resource Specification — validation contracts
--
-- Both Go and Python convert user-facing resource params into
-- proto messages. The contract: given identical user inputs,
-- both must produce identical proto messages.
-- ════════════════════════════════════════════════════════════════════

/-- CPU specification in fractional cores -/
structure CPUSpec where
  request : Float  -- Must be > 0 if set
  limit   : Float  -- Must be >= request if set, 0 means no limit
  deriving Repr

/-- Memory specification in MiB -/
structure MemorySpec where
  requestMiB : Nat   -- Must be > 0 if set
  limitMiB   : Nat   -- Must be >= requestMiB if set, 0 means no limit
  deriving Repr

/-- Timeout specification -/
structure TimeoutSpec where
  seconds : Nat  -- Must be > 0; both languages default 0 → 300
  deriving Repr

def defaultTimeoutSecs : Nat := 300  -- 5 minutes, both Go and Python

-- ════════════════════════════════════════════════════════════════════
-- Validation invariants
-- ════════════════════════════════════════════════════════════════════

/-- CPU limit requires CPU request.
    Both Go and Python enforce this. -/
def cpuLimitRequiresRequest (spec : CPUSpec) : Prop :=
  spec.limit > 0 → spec.request > 0

/-- CPU limit must be >= request.
    Go: explicit check. Python: similar. -/
def cpuLimitGeRequest (spec : CPUSpec) : Prop :=
  spec.limit > 0 → spec.limit ≥ spec.request

/-- Memory limit requires memory request.
    Go: explicit check. Python: similar. -/
def memoryLimitRequiresRequest (spec : MemorySpec) : Prop :=
  spec.limitMiB > 0 → spec.requestMiB > 0

/-- Memory limit must be >= request -/
def memoryLimitGeRequest (spec : MemorySpec) : Prop :=
  spec.limitMiB > 0 → spec.limitMiB ≥ spec.requestMiB

-- ════════════════════════════════════════════════════════════════════
-- CPU to milliCPU conversion — integer truncation risk
--
-- Go: uint32(1000 * params.CPU) — truncates fractional milliCPU
-- e.g., CPU=0.1234 → milliCPU=123 (not 123.4)
--
-- Python: uses protobuf float fields directly (no milliCPU conversion
-- in the client — the server handles it).
--
-- This means Go and Python may send DIFFERENT proto values for the
-- same user input. Invisible when broken: the sandbox gets slightly
-- different CPU allocation depending on which client created it.
-- ════════════════════════════════════════════════════════════════════

/-- Go's milliCPU conversion: truncates to uint32 -/
def cpuToMilliCPU (cpu : Float) : Nat :=
  (cpu * 1000).toUInt32.toNat

-- ════════════════════════════════════════════════════════════════════
-- Network access — mutual exclusion invariant
--
-- BlockNetwork and CIDRAllowlist are mutually exclusive.
-- Go: explicit check with error return.
-- Python: should enforce the same.
-- ════════════════════════════════════════════════════════════════════

/-- Network access modes -/
inductive NetworkAccessType where
  | open      : NetworkAccessType  -- Default, all access allowed
  | blocked   : NetworkAccessType  -- No network access
  | allowlist : NetworkAccessType  -- Only specified CIDRs
  deriving DecidableEq, Repr

/-- Block and allowlist are mutually exclusive -/
def validNetworkAccess (blockNetwork : Bool) (cidrs : List String) : Bool :=
  ¬(blockNetwork ∧ cidrs.length > 0)

/-- Workdir must be absolute path if set -/
def validWorkdir (workdir : String) : Prop :=
  workdir = "" ∨ workdir.startsWith "/"

-- ════════════════════════════════════════════════════════════════════
-- Discovered invariant: timeout zero-value ambiguity
--
-- Go comment: "Ideally we would forbid an explicit zero Timeout,
-- but we can't distinguish between SandboxCreateParams{Timeout: 0}
-- and SandboxCreateParams{} where Timeout gets initialized to zero."
--
-- Both languages map 0 → 300. But this means a user who INTENDS
-- timeout=0 (no timeout) gets 300 seconds silently. The zero value
-- of the Go struct's time.Duration makes this ambiguous.
-- ════════════════════════════════════════════════════════════════════

/-- Timeout resolution: 0 maps to default -/
def resolveTimeout (t : Nat) : Nat :=
  if t == 0 then defaultTimeoutSecs else t

end Spec
