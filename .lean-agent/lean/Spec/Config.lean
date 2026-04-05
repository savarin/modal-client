namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Configuration & Profile — cross-language contract
--
-- Both Go and Python load from ~/.modal.toml with env-var overrides.
-- The invariant: a Profile constructed by either language, given the
-- same inputs, must produce the same resolved values.
-- ════════════════════════════════════════════════════════════════════

/-- A server URL must be either https:// or http:// prefixed.
    Go validates this at connection time; Python does not validate
    until the first RPC call. This is an unguarded invariant. -/
inductive ServerScheme where
  | https : ServerScheme
  | http  : ServerScheme
  deriving DecidableEq, Repr

/-- Parsed server URL — forces scheme validation at construction. -/
structure ServerURL where
  scheme : ServerScheme
  host   : String
  deriving Repr

/-- A Profile requires non-empty TokenID and TokenSecret for any
    authenticated RPC. Go checks this in injectRequiredHeaders;
    Python checks in the interceptor. But neither validates at
    Profile construction time — the error surfaces on first RPC. -/
structure Profile where
  serverURL           : ServerURL
  tokenID             : String
  tokenSecret         : String
  environment         : String
  imageBuilderVersion : String
  logLevel            : String
  deriving Repr

/-- Configuration resolution: env vars > TOML file > defaults.
    The precedence is the same in both languages, but the default
    for imageBuilderVersion is "2024.10" in Go and unset in Python. -/
def resolveField (envVar : Option String) (tomlVal : Option String)
    (default : Option String := none) : Option String :=
  envVar <|> tomlVal <|> default

-- ════════════════════════════════════════════════════════════════════
-- Discovered invariant: imageBuilderVersion default divergence
--
-- Go: firstNonEmpty(env, raw, "2024.10") — hardcoded fallback
-- Python: no default — returns empty string if unset
-- Impact: when both clients operate on the same workspace without
-- explicit imageBuilderVersion, they may trigger different image
-- build paths silently.
-- ════════════════════════════════════════════════════════════════════

/-- Go's behavior: always produces a non-empty imageBuilderVersion -/
theorem go_image_builder_always_set
    (envVar tomlVal : Option String)
    : (resolveField envVar tomlVal (some "2024.10")).isSome = true := by
  sorry

/-- Profile validity: token pair must be present for auth.
    Neither language enforces this at construction — it's a
    convention invariant (documented but not checked). -/
def Profile.hasCredentials (p : Profile) : Prop :=
  p.tokenID ≠ "" ∧ p.tokenSecret ≠ ""

/-- Theorem: any RPC call requires valid credentials.
    Pre: Profile.hasCredentials. The code doesn't check this
    at Profile construction — it checks at RPC time. -/
theorem rpc_requires_credentials
    (p : Profile) (h : p.hasCredentials)
    : p.tokenID ≠ "" ∧ p.tokenSecret ≠ "" := by
  exact h

end Spec
