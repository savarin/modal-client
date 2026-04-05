# Formalization Findings

## Discovered Invariants

### 1. imageBuilderVersion default divergence
**Discovery:** When formalizing `resolveField` with defaults, the Go path `firstNonEmpty(env, raw, "2024.10")` has a hardcoded fallback. Python has no such default — returns empty string if unset.
**Current enforcement:** unguarded (0)
**Lean evidence:** `Config.lean` — `go_image_builder_always_set` theorem requires `some "2024.10"` default; Python path has no equivalent.
**Risk:** Mixed-language deployments using the same workspace without explicit imageBuilderVersion get different image build paths. Silent — both clients succeed but may produce different container images.

### 2. Token refresh produces valid expiry (not validated)
**Discovery:** Formalizing `refreshProducesValidToken` revealed that neither Go nor Python validates that the server-returned token has `expiry > now`. If the server returns a token with past expiry, the client enters a tight refresh loop.
**Current enforcement:** unguarded (0)
**Lean evidence:** `AuthToken.lean` — `refreshProducesValidToken` is a proposition, not enforced by either codebase.
**Risk:** Tight refresh loop consuming server resources. Not a crash — the client keeps working but generates unbounded auth RPCs.

### 3. Retry count divergence (Go: 3, Python: unbounded)
**Discovery:** Formalizing `RetryConfig` forced explicit `maxAttempts` field. Python's `Retry` dataclass has no such field — retries are bounded only by context deadline.
**Current enforcement:** convention (1) — documented but not cross-language enforced
**Lean evidence:** `RetryContract.lean` — `goRetryDefault.maxAttempts = 3` vs Python having no equivalent field.
**Risk:** For calls without a deadline, Python retries indefinitely on Unavailable errors. Go fails after 3 attempts (~1.4s). Silent behavioral divergence — both "work" but with radically different failure characteristics.

### 4. Internal error retry divergence
**Discovery:** Cross-referencing `goRetryable` with `pythonExceptionMapping` revealed that Go retries `codes.Internal` but Python maps it to `InternalError` (not `ServiceError`), meaning Python's retry logic may NOT retry Internal errors the same way.
**Current enforcement:** unguarded (0)
**Lean evidence:** `GrpcErrorMapping.lean` — `internal_retry_divergence` theorem.
**Risk:** Server returning Internal errors gets different retry behavior from Go vs Python clients. Go keeps trying; Python may surface the error to the user immediately.

### 5. Error code group merging (Go callers unaware)
**Discovery:** Formalizing `pythonExceptionMapping` made the code-group merges explicit: InvalidArgument+OutOfRange→InvalidError, FailedPrecondition+Aborted→ConflictError. Go has no such grouping — callers check individual codes.
**Current enforcement:** convention (1) — Python enforces via exhaustive match, Go relies on caller discipline.
**Lean evidence:** `GrpcErrorMapping.lean` — `invalidGroup`, `conflictGroup`, `serviceGroup`.
**Risk:** Go users checking only `codes.InvalidArgument` miss `codes.OutOfRange` errors that Python catches. A Go caller may let an error propagate uncaught that a Python caller would handle.

### 6. Profile credentials not validated at construction
**Discovery:** Formalizing `Profile.hasCredentials` as a precondition revealed it's checked at RPC time (in `injectRequiredHeaders`), not at `Profile` construction.
**Current enforcement:** convention (1) — both Go and Python document the requirement but defer validation.
**Lean evidence:** `Config.lean` — `rpc_requires_credentials` theorem requires explicit precondition `h : p.hasCredentials`.
**Risk:** A client created with empty credentials succeeds at construction but fails on first RPC with a confusing "missing token_id" error. The error is correct but could surface earlier.

### 7. CPU milliCPU truncation divergence
**Discovery:** Formalizing `cpuToMilliCPU` revealed Go converts `float64 → uint32(1000 * cpu)` with truncation, while Python may send float values directly in the proto.
**Current enforcement:** unguarded (0)
**Lean evidence:** `SandboxResource.lean` — `cpuToMilliCPU` definition.
**Risk:** CPU=0.1234 → Go sends milliCPU=123, Python may send 123.4. The sandbox gets slightly different allocation depending on which client created it.

### 8. Timeout zero-value ambiguity
**Discovery:** Formalizing `resolveTimeout` surfaced Go's own comment about the ambiguity: `Timeout: 0` (user intent: no timeout) and `SandboxCreateParams{}` (default: no timeout specified) are indistinguishable.
**Current enforcement:** convention (1) — documented in Go code comment but not enforced.
**Lean evidence:** `SandboxResource.lean` — `resolveTimeout` maps 0 → 300.
**Risk:** User who explicitly wants no timeout gets 5 minutes silently. Both languages have this issue.

## Lean Spec Summary
- Files: Config.lean, AuthToken.lean, RetryContract.lean, SandboxResource.lean, GrpcErrorMapping.lean (+ root Spec.lean)
- `lake build`: pass (0 errors, 6 sorry warnings — all proofs are sorry as expected)
- sorry count: 6
