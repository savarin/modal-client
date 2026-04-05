# Improvement Targets

Baseline IES: 0.3590 (14/39)
Theoretical max IES: 1.0000 (39/39)

## Strategic assessment

Risk concentrates at two boundaries: **input validation for Go SDK parameters** (ports, credentials, secrets) and **proto construction determinism** (volume/cloud-bucket map iteration). The Go SDK is newer than the Python SDK and lacks several validations that Python enforces. The highest-value targets are the 5 unguarded invariants — each is a +2 improvement for low implementation cost. The ordering invariants (volume/cloud-bucket) are invisible when broken: the sandbox works fine but proto messages are nondeterministic, which could break server-side caching or idempotency checks.

## Theoretical max table

| Check function | Max returnable score | Score-2 reachable? | What triggers score 3 |
|---|---|---|---|
| check_01_port_bounds | 3 | Yes | Port params use uint16 or PortNumber named type |
| check_02_volume_ordering | 3 | Yes | sort.Slice on volumeMounts |
| check_03_cloud_bucket_ordering | 3 | Yes | sort.Slice on cloudBucketMounts |
| check_04_token_refresh_expiry | 3 | Yes | FutureTimestamp newtype for expiry |
| check_05_profile_credentials | 3 | Yes | Credential validation in NewClientWithOptions |
| check_06_timeout_zero_value | 3 | Yes | *time.Duration pointer type for Timeout |
| check_07_cpu_request | 3 | Yes | PositiveCPU or CPUCores named type |
| check_08_memory_request | 3 | Yes | PositiveMemory or MemoryMiB named type |
| check_09_workdir_absolute | 3 | Yes | AbsolutePath named type |
| check_10_network_exclusion | 3 | Yes | NetworkAccessMode sum type |
| check_11_server_url_scheme | 3 | Yes | ServerURL struct parsed at construction |
| check_12_close_idempotency | 3 | Yes | sync.Once wrapping Close |
| check_13_secret_nil_handling | 3 | Yes | []Secret value type (not []*Secret) |

## Phase 1 targets (execute sequentially)

### Target 1: port_bounds_validation (0→2)
**Invariant:** Port values must be in range [0, 65535] before uint32 cast
**Category:** input validation
**Strategy:** validated
**Where:** `grep -n 'uint32(port)' go/sandbox.go`
**What:** Add port range validation before the uint32 cast in buildSandboxCreateRequestProto. Check each port slice (EncryptedPorts, H2Ports, UnencryptedPorts) for port < 0 || port > 65535. Return error if invalid.
**Test:** Add test case in go/test/ with negative and >65535 port values

### Target 2: volume_mount_ordering (0→2)
**Invariant:** Volume mounts must be deterministically ordered in proto
**Category:** ordering
**Strategy:** validated
**Where:** `grep -n 'range params.Volumes' go/sandbox.go`
**What:** After building volumeMounts slice, sort by MountPath before assigning to proto. Use `slices.SortFunc(volumeMounts, func(a, b) int { return cmp.Compare(a.MountPath, b.MountPath) })` or `sort.Slice`.
**Test:** Test with multiple volumes and verify consistent proto output

### Target 3: cloud_bucket_ordering (0→2)
**Invariant:** CloudBucketMounts must be deterministically ordered in proto
**Category:** ordering
**Strategy:** validated
**Where:** `grep -n 'range params.CloudBucketMounts' go/sandbox.go`
**What:** Same sorting pattern as Target 2 but for cloudBucketMounts slice. Sort by mount path.
**Test:** Test with multiple cloud bucket mounts

### Target 4: token_refresh_expiry (0→2)
**Invariant:** Fetched token expiry must be in the future
**Category:** input validation
**Strategy:** validated
**Where:** `grep -n 'func.*FetchToken' go/auth_token_manager.go`
**What:** After decoding JWT expiry, check `if expiry <= time.Now().Unix()`. Log a warning and use DefaultExpiryOffset fallback (same as missing exp field).
**Test:** Test with a mock token that has past expiry

### Target 5: profile_credentials (0→2)
**Invariant:** Profile must have non-empty credentials to be usable
**Category:** input validation
**Strategy:** validated
**Where:** `grep -n 'func NewClientWithOptions' go/client.go`
**What:** After resolving profile, check `if profile.TokenID == "" || profile.TokenSecret == ""` and return an error. Skip check when ControlPlaneClient is provided (testing).
**Test:** Test NewClient with empty credentials

### Target 6: secret_nil_handling (1→2)
**Invariant:** Nil secrets in params must produce an error, not be silently skipped
**Category:** input validation
**Strategy:** validated
**Where:** `grep -n 'secret != nil' go/sandbox.go`
**What:** Change the nil check from silent skip to an error return: `if secret == nil { return nil, fmt.Errorf("Secrets slice contains nil entry at index %d", i) }`
**Test:** Test sandbox create with nil secret in slice

### Target 7: timeout_zero_value (1→2)
**Invariant:** Explicit Timeout=0 should produce a log warning
**Category:** contract consistency
**Strategy:** validated
**Where:** `grep -n 'timeoutSecs == 0' go/sandbox.go`
**What:** Add a debug log message before defaulting: `// We can't distinguish 0 from unset, but log for observability`
**Test:** Verify log output contains timeout default message

## Phase 2 ideas (explore after Phase 1)

- Promote port_bounds to structural (3): use a PortNumber newtype with validated constructor
- Promote close_idempotency to structural (3): wrap in sync.Once
- Promote server_url_scheme to structural (3): introduce ServerURL struct in config.go
- Promote cpu/memory to structural (3): introduce PositiveCPU/PositiveMemory named types
- Promote volume/cloud_bucket ordering to structural (3): sort in constructor, not call site
