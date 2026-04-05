namespace Spec

-- ════════════════════════════════════════════════════════════════════
-- Auth Token Manager — state machine with concurrent access
--
-- The token manager has three states based on expiry:
--   Valid (far from expiry) → NearExpiry (within RefreshWindow) → Expired
--
-- Go: atomic.Pointer + sync.Mutex (double-checked locking)
-- Python: similar pattern with threading.Lock
--
-- Key constants:
--   RefreshWindow = 300 seconds (5 minutes before expiry)
--   DefaultExpiryOffset = 1200 seconds (20 minutes, for tokens without exp)
-- ════════════════════════════════════════════════════════════════════

/-- Token state machine -/
inductive TokenState where
  | empty     : TokenState  -- No token fetched yet
  | valid     : TokenState  -- Token exists, far from expiry
  | nearExpiry: TokenState  -- Within RefreshWindow, still usable
  | expired   : TokenState  -- Past expiry, must block on refresh
  deriving DecidableEq, Repr

structure TokenAndExpiry where
  token  : String
  expiry : Int  -- Unix timestamp
  deriving Repr

def RefreshWindow : Int := 300  -- 5 minutes

def classifyToken (now : Int) (te : TokenAndExpiry) : TokenState :=
  if te.token == "" then TokenState.empty
  else if now >= te.expiry then TokenState.expired
  else if now >= te.expiry - RefreshWindow then TokenState.nearExpiry
  else TokenState.valid

-- ════════════════════════════════════════════════════════════════════
-- Concurrent access contract
--
-- GetToken behavior by state:
--   empty/expired → all callers block, one fetches (mutex)
--   nearExpiry → one caller refreshes (tryLock), others get old token
--   valid → return immediately, no locking
--
-- Invariant: a caller in state `valid` or `nearExpiry` always gets
-- a non-empty token. A caller in state `expired` blocks but eventually
-- gets a non-empty token (assuming the RPC succeeds).
-- ════════════════════════════════════════════════════════════════════

/-- Valid or nearExpiry tokens are non-empty -/
theorem valid_token_nonempty (now : Int) (te : TokenAndExpiry)
    (h : classifyToken now te = TokenState.valid ∨
         classifyToken now te = TokenState.nearExpiry)
    : te.token ≠ "" := by
  sorry

/-- A refreshed token has a future expiry.
    This is assumed by both Go and Python but NOT validated —
    if the server returns a token with expiry <= now, the client
    enters a tight refresh loop. Unguarded invariant. -/
def refreshProducesValidToken (now : Int) (newTE : TokenAndExpiry) : Prop :=
  newTE.token ≠ "" ∧ newTE.expiry > now

-- ════════════════════════════════════════════════════════════════════
-- Discovered invariant: JWT decode failure handling
--
-- Go: if JWT decode fails (not 3 parts, base64 error, no exp claim),
--     returns 0 → defaultExpiry = now + 1200. Silent fallback.
-- Python: similar behavior, but the exact fallback offset matters.
--
-- If the offsets differ, the two clients will attempt refresh at
-- different times for the same token — potentially causing
-- unnecessary concurrent refresh storms in mixed-language deployments.
-- ════════════════════════════════════════════════════════════════════

/-- JWT with valid structure has exactly 3 dot-separated parts -/
def validJWTStructure (token : String) : Prop :=
  (token.splitOn ".").length = 3

/-- Transition: only Expired or Empty can trigger a blocking refresh -/
def requiresBlockingRefresh (state : TokenState) : Bool :=
  match state with
  | TokenState.empty   => true
  | TokenState.expired => true
  | _                  => false

/-- Transition: NearExpiry triggers non-blocking refresh attempt -/
def allowsBackgroundRefresh (state : TokenState) : Bool :=
  match state with
  | TokenState.nearExpiry => true
  | _                     => false

end Spec
