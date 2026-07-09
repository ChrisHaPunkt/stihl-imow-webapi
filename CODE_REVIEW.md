# Full Code Review — `imow-webapi`

Unofficial **async** Python wrapper for the STIHL iMOW cloud WebAPI (RMI / Gen ≤4
mowers), published to PyPI as `imow-webapi` and consumed by the sibling
`ha-stihl-imow` Home Assistant integration.

This is a whole-library review covering **API design, correctness, type safety,
error handling, performance, packaging, tests, security, and Home Assistant
integration fit**. It complements the existing `REVIEW.md` (which is a deep-dive
into the authentication flow specifically) and does not duplicate its detailed
auth-hardening plan — where it overlaps, it references it.

Verified against the code at `imow/` and the aiohttp docs (current stable,
3.13.x) for the session / cookie-jar / response-lifecycle claims.

---

## TL;DR

The library is small, pragmatic, and functional, and the **auth flow has already
been meaningfully hardened** (isolated-cookie clearing, an `asyncio.Lock` around
re-auth, a 401-retry path, a typed `LoginError` with diagnostics, backoff on
transient GET failures, an OAuth `state`). Good.

The **highest-value remaining work is not in auth** — it is:

1. **Packaging/runtime mismatch** — `requires-python = ">=3.14"` is almost
   certainly wrong for a Home Assistant library and will make the package
   uninstallable for essentially all HA users (HA currently targets 3.13). This
   is the single biggest release blocker.
2. **The `MowerState` dynamic-attribute model** is fragile: every field is an
   upstream dict key promoted to an attribute, so any missing field is an
   `AttributeError` at access time, and the "type stubs" at the bottom of the
   class are actively misleading (they assign `set`/`dict` objects as defaults,
   not types).
3. **Response handling is non-idiomatic** — `api_request` returns a
   connection-released `ClientResponse` and callers re-parse `await
   response.text()` everywhere; every read does `json.loads(await
   response.text())` by hand instead of `response.json()`.
4. **No real unit tests.** `tests/test_unit_imow.py` contains only `setUp` and
   asserts nothing; the meaningful tests are all live-integration tests that need
   real STIHL credentials.
5. **Lint/format drift** — `black --check` reports 3 files need reformatting and
   `flake8` flags `E721` (`type(...) == str`) plus long lines.

None of these are catastrophic, but (1) blocks installation and (2)–(4) are the
recurring source of the "works until STIHL changes a field / a poll races" class
of bug that the HA integration sees.

---

## Scorecard

| Area | Grade | Notes |
|------|:----:|-------|
| Auth flow robustness | B+ | Already hardened (lock, cookie clearing, 401 retry, typed error). See `REVIEW.md`. |
| API/data model design | C | `MowerState` dynamic attrs + misleading stubs; God-object `IMowApi`. |
| Correctness | C+ | A few real bugs (maintenance recursion, `close()` sleep, naive datetimes). |
| Type safety | C- | `Optional` params typed as bare types; `any` (builtin) used as annotation; stubs wrong. |
| Error handling | B- | Typed exceptions exist; some bare/incorrect except targets; `fetch_messages` can return silently. |
| Performance | B | Fine for polling; redundant full-mower fetches; blocking-ish patterns minimal. |
| Packaging | C | Wrong `requires-python`; version pin coupling with HA. |
| Tests | D | No offline unit coverage; integration-only, credential-gated. |
| Docs / docstrings | C+ | Some good docstrings; several missing/typo’d; non-PEP257 formatting. |
| Security | B | Redacts tokens; but logs may leak PII (coords); implicit grant (upstream constraint). |

---

## 1. Packaging & runtime (RELEASE BLOCKER)

### 1.1 `requires-python = ">=3.14"` is almost certainly wrong — HIGH
`pyproject.toml`:
```toml
requires-python = ">=3.14"
```
and `imow/common/package_descriptions.py` hard-asserts it at import:
```python
python_major = "3"
python_minor = "14"
...
assert sys.version_info >= (int(python_major), int(python_minor))
```

- Home Assistant currently runs on **Python 3.13** (3.12 only just aged out).
  A library that *requires* 3.14 cannot be installed into any current HA
  environment, so `imow-webapi==0.9.0` in the integration `manifest.json` would
  fail to resolve for users.
- Even the dev machine here runs **3.12.13**, so `pytest`/`black` run only
  because `uv` provisions a separate interpreter.
- Nothing in the code actually needs 3.14. The syntax used (`X | Y` unions,
  `tuple[...]` generics, `from __future__ import annotations`) is fine on 3.9+.

**Recommendation:** set `requires-python = ">=3.11"` (or match HA's floor, 3.13,
if you want to be conservative), and update `package_descriptions.py`
accordingly. Keep one source of truth — right now the floor is duplicated in
`pyproject.toml`, `package_descriptions.py`, and the classifier list, and they
must not drift.

### 1.2 The hard `assert` on version is the wrong mechanism — MEDIUM
```python
try:
    assert sys.version_info >= (int(python_major), int(python_minor))
except AssertionError:
    raise RuntimeError(...)
```
- `assert` is stripped under `python -O`, so this "guard" silently disappears in
  optimized runs. Wrapping it in try/except to re-raise `RuntimeError` is a code
  smell — just do the comparison directly:
  ```python
  if sys.version_info < (3, 11):
      raise RuntimeError(...)
  ```
- Better still: rely on `requires-python` metadata and drop the runtime check
  entirely. pip/uv enforce it at install time, which is the right layer.

### 1.3 Version single-sourcing — OK, keep it
`[tool.hatch.version] path = "imow/common/package_descriptions.py"` reading
`__version__` is clean. Just make sure the HA `manifest.json`
`imow-webapi==x.y.z` pin is bumped in lockstep (it currently pins `0.9.0`).

### 1.4 `secrets.py` at repo root shadows stdlib `secrets` — MEDIUM (design smell)
The integration tests do `from secrets import *` and `main.py` does `import
secrets as creds`, so a repo-root `secrets.py` **shadows the stdlib `secrets`
module** on the import path. The auth code even comments that it deliberately
uses `os.urandom` "to avoid clashing with a repo-root `secrets.py`". That is a
workaround for a self-inflicted footgun.

**Recommendation:** rename the credentials file (e.g. `test_secrets.py` or, far
better, read `EMAIL`/`PASSWORD` from env vars / a `.env` via `os.environ`). Then
the code is free to use the stdlib `secrets` module (the correct tool for CSRF
`state` / tokens) without contortions. `secrets.py` is git-ignored, but the
shadowing risk applies to anyone importing `secrets` anywhere in-process.

---

## 2. Data model: `MowerState` — the biggest design risk

`imow/common/mowerstate.py`.

### 2.1 Dynamic attributes make every optional field a landmine — HIGH
```python
def replace_state(self, upstream: dict):
    self.__dict__.update(
        map(lambda kv: (kv[0].replace(" ", "_"), kv[1]), upstream.items())
    )
```
Every upstream key becomes an attribute. Consequences:

- Referencing any field STIHL didn't return raises `AttributeError` at access
  time, far from the source. `update_setting` reads ~19 named attributes
  (`mower_state.corridorMode`, `.gpsProtectionEnabled`, …); if STIHL drops or
  renames one, the failure surfaces deep inside a PUT builder, not at parse time.
- No IDE/mypy support for real (the "stubs" are broken — see 2.2).
- `replace_state` blindly trusts keys; a hostile/renamed key like `imow` or
  `status` from upstream would silently clobber internal state (`self.imow`,
  the back-reference!). That is a latent correctness/security concern.

**Recommendation (incremental):**
- Add a typed accessor for the fields the code and HA actually use, or model the
  payload with a `@dataclass` / `pydantic`/`mashumaro` model and keep the raw
  dict alongside for forward-compat. Even a thin `dataclasses.dataclass` with
  explicit `Optional` fields + a `from_upstream(cls, dict)` classmethod removes
  the whole class of `AttributeError` bugs and gives real types.
- At minimum, guard the known-optional fields (`.get(...)` semantics) and never
  let upstream keys overwrite `self.imow` / reserved names (filter them in
  `replace_state`).

### 2.2 The "type hint stubs" are misleading and wrong — MEDIUM
The block at the bottom of `MowerState`:
```python
accountId: str = {str}
asmEnabled: bool = {bool}
boundryOffset: bool = {int}   # 60
coordinateLatitude: float = {float}
team = {None}
```
- These are **not type hints with defaults** — they assign runtime values:
  `{str}` is a *set literal containing the `str` type object*, `{None}` is
  `{None}`. If any instance ever fails to receive the field from upstream, the
  attribute value is a `set`, not `""`/`0`/`None`. That will produce baffling
  downstream bugs (e.g. `mower.accountId` == `{<class 'str'>}`).
- The annotations themselves are wrong: `boundryOffset: bool` /
  `corridorMode: bool` are annotated `bool` but documented/valued as `int`.
  Typos too: `boundryOffset` (boundary).
- They give a false sense of an interface while providing no static-checking
  benefit (they’re class attributes, shadowed by instance `__dict__` at runtime).

**Recommendation:** delete this block and replace with either (a) a real
dataclass/`TypedDict` describing the payload, or (b) nothing plus a docstring
listing known fields. As-is it is worse than absent.

### 2.3 `update_state_messages` hard-depends on `status` shape — MEDIUM
```python
if self.status["mainState"] != self.ERROR_MAINSTATE_CODE:
    ... self.imow.messages_user.get_status_message(short_code=self.status["mainState"])
```
- Assumes `self.status` exists and has `mainState`/`extraStatus`. If the mower
  payload lacks `status` (partial response, new device), this throws `KeyError`
  inside the constructor (`__init__` → `replace_state` → `update_state_messages`),
  so **object construction itself fails**. Constructors doing network-shaped
  parsing should be defensive.
- `get_status_message` returns the **short** message twice (returns
  `(viking_..._short, viking_..._short)` — the "long" is a copy). Likely a bug
  (`_long` intended for the second element).

### 2.4 `MowerState.imow` back-reference couples model to client — LOW/DESIGN
`MowerState` holds `self.imow` and calls back into it (`get_statistics`,
`intent`, `update_from_upstream`). This is convenient but couples the data model
to the client and is exactly why the HA integration has a commented-out
`del mower_state.__dict__["imow"]` (it can't cleanly serialize/stash the state).
Consider splitting "plain data" from "active record" behavior, or documenting
that `MowerState` is intentionally an active-record object and must not be
serialized.

---

## 3. HTTP / response handling (`api_request` and callers)

`imow/api/__init__.py`.

### 3.1 Returning a connection-released response is fragile — MEDIUM
```python
response = await self.http_session.request(method, url, headers=..., data=payload)
await response.read()          # buffer body
response.raise_for_status()
return response                # connection already released
```
Then every caller does `json.loads(await response.text())`. This works *only*
because `read()` buffers the body before the connection is released (confirmed
against aiohttp docs: `read()` "releases the connection" and caches the payload,
so later `text()`/`json()` reads the cache). But it is brittle and non-idiomatic:

- The canonical aiohttp pattern is `async with session.request(...) as resp:`
  and consume inside the block, or return the *parsed payload*, not the response.
- Returning a released `ClientResponse` invites a future caller to `await
  resp.read()` again or access streaming attrs and get surprised.

**Recommendation:** have `api_request` return parsed data (bytes/text/JSON) from
inside the request context, and give callers a small helper (e.g.
`_get_json(url)`). This removes ~10 hand-rolled `json.loads(await
response.text())` sites and the `.ok`/`.status` checks that only work by luck.
This is finding #6 in `REVIEW.md`; I’m reinforcing it because it touches every
read method, not just auth.

### 3.2 Use `response.json()` instead of `json.loads(await response.text())` — LOW
Repeated in `receive_mowers`, `receive_mower_by_id`, `receive_mower_statistics`,
`check_api_maintenance`, `update_setting`, etc. `aiohttp`'s `resp.json()` handles
decoding and is clearer. (If the server sends a wrong content-type, pass
`content_type=None`.)

### 3.3 `check_api_maintenance` can recurse into itself — MEDIUM (correctness)
```python
async def check_api_maintenance(self):
    ...
    response = await self.api_request(url, "GET", headers=headers, authenticated=False)
```
`check_api_maintenance` calls `api_request`, and `api_request` calls
`check_api_maintenance` on HTTP 500:
```python
if e.status == 500:
    await self.check_api_maintenance()
```
If the **maintenance endpoint itself** returns 500, you get
`api_request → 500 → check_api_maintenance → api_request → 500 → …` until the
recursion limit / connection errors. The maintenance probe should bypass the
500-handler (e.g. an internal flag `_probe=True` that skips the maintenance
re-entry), analogous to how `_is_retry` guards the 401 path.

### 3.4 `close()` sleeps unconditionally and couples to internals — LOW
```python
async def close(self):
    if self._owns_session and self.http_session and not self.http_session.closed:
        await asyncio.sleep(0.250)
        await self.http_session.close()
```
- The `await asyncio.sleep(0.250)` is a historical workaround for aiohttp’s
  "unclosed connector" warning on the *legacy* connector; on modern aiohttp
  (which the project pins, `aiohttp~=3.9`) `await session.close()` is sufficient.
  The sleep just adds latency to teardown. Drop it, or gate it behind a comment
  explaining the exact aiohttp version it works around.
- The `_owns_session` guard (don't close a caller-injected session) is **correct
  and good** — this directly fixes the HA "closed the shared session" hazard.

### 3.5 Header duplication — LOW
`api_request` builds a big browser-mimicking header dict, and `update_setting`
builds a near-identical one again (different UA string). Extract a single
`_default_headers()` (or a class constant) and override only what differs. Less
drift, one place to update the UA.

### 3.6 Retry policy asymmetry is reasonable but undocumented publicly — LOW
GETs get 3 attempts with exponential backoff + jitter; non-GET gets 1. Good
default (don’t retry non-idempotent intents). Worth a one-line docstring note so
callers know POST intents are single-shot.

---

## 4. `intent()` — the action builder

`imow/api/__init__.py:502`.

### 4.1 It’s a 160-line multi-branch method — MEDIUM (maintainability)
`intent` parses `**kwargs`, cross-maps them onto `first/second_action_value_param`,
then branches per action to build a positional CSV `actionValue`. It’s doing four
jobs. Splitting per-action value builders (`_build_start_mowing_value(...)`,
`_build_start_from_point_value(...)`) would make each testable in isolation and
shrink the cyclomatic complexity a lot.

### 4.2 `test_mode` changes the return type — MEDIUM (API design)
```python
if not test_mode:
    ...
    return response          # ClientResponse
else:
    ...
    return True              # bool
```
A method that returns `ClientResponse` normally but `True` in test mode is a typed
lie (the annotation says `-> aiohttp.ClientResponse`). Callers can’t treat the
result uniformly. Either return a consistent type (e.g. always the response, or a
small result object) or make `test_mode` a separate `dry_run` method.

### 4.3 Kwarg translation is silent and lossy — LOW
The `for key, value in given_kwargs:` loop only recognizes
`duration/startpoint/endtime/starttime`. An unknown/misspelled kwarg
(`start_point`, `start_time`) is silently ignored — the user gets default
behavior with no warning. Validate the kwarg names and warn/raise on unknowns.

### 4.4 `first_action_value_param: any` uses the builtin `any` — LOW (type bug)
```python
first_action_value_param: any = "",
```
`any` is the builtin function, not `typing.Any`. As an annotation it’s
meaningless (mypy will complain). Same in `MowerState.intent`. Use `Any` (import
from `typing`) or a precise `str | int`.

### 4.5 Naive `datetime.now()` for defaults — MEDIUM (correctness)
`START_MOWING` with no time defaults to "2 hours from now" using
`datetime.now()` (local, naive). It even warns about timezone ambiguity in the
log. For a cloud API tied to `mower.timeZone`, this is a real correctness risk
around DST boundaries and for servers in other TZs. Prefer timezone-aware UTC or
the mower’s declared timezone, and format explicitly. (`REVIEW.md` finding #10
notes the same for expiry math; it applies here too.)

### 4.6 `mower_external_id` length check message — LOW
```python
if len(mower_external_id) < 16:
    raise AttributeError(f"...need exactly 16 chars, got {len(...)}...")
```
Message says "exactly 16" but the check is `< 16` (17+ passes). Also
`AttributeError` is the wrong type — this is a bad argument, so `ValueError`. The
AGENTS.md says "must be exactly 16 chars — code asserts this"; the code doesn’t
(it allows longer). Tighten to `!= 16` and raise `ValueError`.

---

## 5. Correctness bugs & smells (misc)

- **`get_status_by_id` type check** (`imow/api/__init__.py:723`):
  `if not type(mower_id) == str:` — `flake8 E721`, and it should be
  `if not isinstance(mower_id, str):`. The default arg is also wrong:
  `mower_id=(str, int)` sets the *default value* to the tuple `(str, int)`; it
  reads like a type annotation but isn’t. Should be `mower_id: str | int`.
- **`get_status_by_id` catches `ConnectionError`** to raise `LookupError`, but
  `receive_mower_by_id` raises `ClientResponseError` (an aiohttp error, not
  `ConnectionError`) on a 404. So the intended "not found → LookupError"
  translation never triggers; the raw `ClientResponseError` propagates (the
  integration test `test_get_status_by_wrong_id` in fact asserts
  `ClientResponseError`). The `except ConnectionError` is dead code. Same pattern
  in `get_mower_action_id_from_id`. Decide on one error contract and implement it.
- **`fetch_messages` can silently return `None` state** — on a
  `ClientResponseError` that is *not* 404, the `except` block does nothing (no
  re-raise), leaving `self.messages_en` unset; the next `update_state_messages`
  then throws `AttributeError: 'NoneType' has no attribute 'get_status_message'`.
  Re-raise non-404 errors.
- **`validate_token` mutates then restores `self.access_token`** to test an
  explicit token — not concurrency-safe (another coroutine could observe the
  temporary token). Given the new `_auth_lock`, consider validating without
  mutating shared state (pass the token through), or document it’s not safe under
  concurrency.
- **`api_logout` posts even mid-refresh** — it’s now guarded by `if
  self.csrf_token`, good; but it uses `_ensure_session()` which may *create* a
  session purely to log out. Minor.
- **`update_setting` hardcodes `"mowingTimeManual": None, "mowingTime": None`** in
  the PUT payload regardless of current values — this could unintentionally clear
  server-side mowing-time settings when toggling an unrelated setting. Verify
  against the API contract; if these must be echoed back, read them from
  `mower_state.smartLogic` rather than nulling them.

---

## 6. Type safety

- Constructor params typed as bare types but default to `None`:
  `email: str = None`, `password: str = None`, `token: str = None`,
  `aiohttp_session: ClientSession = None`. These should be `Optional[str]` /
  `str | None` etc. (PEP 484 no longer allows implicit `Optional`).
- `self.token_expires: datetime = None`, `self.messages_user = None` — same.
- Return types: `get_status_by_name -> dict` etc. are fine; but several methods
  return `dict` where the payload is actually a `list` (`receive_mower_start_points
  -> dict` returns a list of start points; `receive_mowers` correctly says
  `List[MowerState]`). Fix the annotations to match reality.
- `any` used as annotation (see 4.4).
- Consider shipping a `py.typed` marker so downstream (the HA integration) gets
  the types you *do* provide. Right now even correct hints aren’t exported.

**Net:** the project would benefit enormously from running `mypy`
(even `--ignore-missing-imports`) in CI; almost every issue above is a one-line
fix that mypy would have surfaced.

---

## 7. Error handling

- Good: dedicated exceptions (`LoginError`, `ApiMaintenanceError`,
  `LanguageNotFoundError`, `MessageNotFoundError`) and the recently added typed,
  diagnostic-rich `LoginError` in the CSRF scraper.
- `exceptions.py` — consider a common base `IMowError(Exception)` so consumers
  (HA) can `except IMowError` broadly. Currently each derives straight from
  `Exception`, so the integration must import and catch each individually.
- `MessageNotFoundError` on an unknown `mainState`/`extraStatus` will bubble out
  of `MowerState.__init__` and break the *whole* poll for one unknown code.
  Degrade gracefully (unknown → a neutral "UNKNOWN" machineState) so a single new
  firmware status code doesn’t take the integration offline.
- Avoid raising `AttributeError`/`LookupError` for *argument* problems; use
  `ValueError`. `AttributeError` in particular can be swallowed by `hasattr`/
  `getattr` call sites and is semantically wrong.

---

## 8. Messages / i18n (`messages.py`)

- The `success_messages` / `error_messages` tables are **~1,650 lines of
  hardcoded German Message() literals** embedded in code. This is data, not logic,
  and it’s a maintenance and review hazard (there are visible typos in the data:
  `"Interner Fehl\`er"` line ~315, trailing spaces, inconsistent `priority`
  types — sometimes `int`, sometimes the string `"---"`).
  - Move this to a bundled data file (`messages.json`/`.py` data module) and load
    it; keep `messages.py` as logic only.
  - The `priority` field mixing `int` and `"---"` means any numeric use of
    `priority` would break; it appears unused, but it’s a trap.
- `get_status_message` returns the short text for **both** short and long
  (see 2.3) — likely wants `_short` and `_long`.
- Lookups are **O(n) linear scans** over the message list per call
  (`for message in self.error_messages:`), executed on every state refresh. Build
  a `dict` keyed by `shortCode` once in `__init__` for O(1). Minor at this scale
  but trivially better.
- `get_error_message`/`get_status_message` index `self.i18n[f"..."]` with `[]`;
  a missing key raises `KeyError` (not the module’s `MessageNotFoundError`).
  Normalize to the typed error.

---

## 9. Performance

Mostly fine for a cloud-polling client, but:

- **Redundant full-mower fetches.** `get_token` → `validate_token` →
  `receive_mowers()` fetches *all* mowers just to validate a token (`REVIEW.md`
  #9). And several convenience methods (`get_status_by_name`,
  `get_mower_action_id_from_name`, `get_mower_id_from_name`) each call
  `receive_mowers()` (a full round-trip) and linear-scan. If the HA integration
  resolves a mower by name then by id, that’s multiple full fetches per action.
  Cache the mower list briefly or resolve once.
- **`fetch_messages` runs on first `api_request`** and downloads i18n JSON
  (potentially two files). Fine once, but it’s gated on `self.messages_en` truthy;
  a failed fetch (non-404) leaves it falsy and re-downloads every call. Cache the
  negative result or fail loudly.
- The `map(lambda ...)` in `replace_state` is fine; a dict comprehension would be
  more readable (`{k.replace(" ", "_"): v for k, v in upstream.items()}`).

---

## 10. Tests

- **`tests/test_unit_imow.py` has no assertions** — only `setUpClass`/`setUp`.
  `pytest tests/test_unit*` collects **zero** tests. There is effectively no
  offline coverage.
- All real coverage is in `tests/test_integration_imow.py`, which needs live
  STIHL credentials and *mutates a real mower* (`test_intent_to_dock_by_id`,
  `test_intent_start_mowing_from_point`) — not runnable in CI, and risky.
- Tests use `unittest` + `loop.run_until_complete` while the project configures
  `pytest-asyncio` (`asyncio_mode = "auto"`). Mixing styles; `get_event_loop()`
  is deprecated on 3.12+. Prefer `async def test_...` with `pytest-asyncio`.
- `assertIs(len(token), 98)` uses identity comparison on ints — works only due to
  small-int caching for values ≤256; use `assertEqual`.

**Recommendation:** add offline unit tests with `aioresponses` (or aiohttp’s test
utils) to mock the STIHL endpoints and cover:
- CSRF scrape success + each failure mode (SPA shell, maintenance, missing
  fields → `LoginError`);
- token parse from redirect fragment; 401 → re-auth-once-retry; 500 → maintenance
  check (and the recursion guard from 3.3);
- `intent` action-value construction for all four `IMowActions` (pure string
  logic — easy, high value);
- `MowerState.replace_state` / message resolution with a fixture payload.

This is where the review’s effort pays back the most: the intent-string builder
and the CSRF/token parsing are pure functions of their inputs and are exactly the
parts that silently break.

---

## 11. Security & privacy

- **Good:** tokens/CSRF are redacted in logs; credentials aren’t logged.
- **PII in DEBUG logs:** `main.py` and the library log mower GPS coordinates and
  names at DEBUG. For an HA library, document that DEBUG logging includes
  location data, and avoid logging coordinates from within the library itself.
- **`replace_state` trusts upstream keys** and can overwrite `self.imow` (see
  2.1) — filter reserved keys.
- **Implicit OAuth grant** (`response_type=token`, long-lived ~30d token, no
  refresh) is a deprecated flow, but it’s **imposed by STIHL’s server**, not a
  choice of this library. The `state` param is now generated (good). Verifying
  `state` on the returned redirect would close the loop (`REVIEW.md` #8).
- **User-Agent spoofing** (pretending to be Firefox 88) is inherent to scraping
  this API; note it as an upstream fragility, since STIHL could block it.

---

## 12. Home Assistant integration fit

Checked against the sibling `ha-stihl-imow` (`custom_components/stihl_imow/`).

- **The integration injects the *shared* session** — `async_setup_entry` and
  `config_flow.py` both use `async_get_clientsession(hass)`. That is the exact
  cookie-leak vector the auth review (`REVIEW.md` #1) is defending against on the
  library side. The library now clears STIHL cookies before each auth (good
  defense), **but** the aligned fix is for the integration to inject
  `async_create_clientsession(hass)` (dedicated cookie jar). Both halves are
  needed; the library can’t fully guarantee isolation while sharing HA’s global
  jar. Track this as a cross-repo action.
- **`config_flow.py` calls `await imow.close()` on the shared session** (line
  ~70). The library’s new `_owns_session` guard makes `close()` a **no-op** for
  injected sessions — which is correct and now *protects* HA from closing its own
  global session. Confirm the integration doesn’t rely on `close()` actually
  tearing down (it shouldn’t).
- **The integration re-authenticates on every setup** — `async_setup_entry` calls
  `get_token(force_reauth=True)` unconditionally, and doesn’t persist the ~30-day
  token. Combined with the library’s implicit-grant re-scrape, that’s a full
  HTML-scrape login on every HA restart. Persisting the token
  (`IMowApi(token=...)`) and only forcing reauth on `LoginError` would cut load
  and reduce exposure to the scrape breaking. (This is an integration-side fix,
  but the library already supports it via the `token=` constructor arg — good.)
- **`MowerState.imow` back-reference** is why the coordinator has a commented-out
  `del mower_state.__dict__["imow"]`. If you ever make `MowerState` a plain data
  object (2.4), the integration gets simpler and can serialize state.
- **Error contract:** the integration maps `LoginError → ConfigEntryAuthFailed`
  and `ApiMaintenanceError → UpdateFailed`. A shared `IMowError` base (finding in
  §7) plus a documented "these are the exceptions we raise" section would make
  that mapping robust to new error types.

The library is a well-behaved *injectable* client after the auth work; the
remaining integration coupling (shared jar, forced reauth, model back-ref) is
mostly on the HA side and already documented in that repo’s own `REVIEW.md`.

---

## 13. Style / lint / hygiene

- `black --check imow` → **3 files would be reformatted** (`mowerstate.py`,
  `api/__init__.py`, and one more). Run `black` before release; add a CI check.
- `flake8` → `E721` (`type(...) == str`), several `E501` long lines (the docstrings
  in `intent`). Configure `flake8` `max-line-length` to match `black` (88) or add
  `# noqa` where intentional; fix `E721`.
- Docstrings: mix of styles; some are missing (`receive_*`, `get_status_*`),
  several have typos (`tobe`, `formated`, `Munites`, "afer", "This has to be until
  time travel"). Adopt one convention (Google/NumPy) and add `Raises:` sections —
  callers need to know `LookupError`/`LoginError`/`ClientResponseError` can come
  out.
- `main.py` uses `import secrets as creds` — see 1.4.
- Windows event-loop policy shim (`WindowsSelectorEventLoopPolicy`) is set at
  import time as a side effect. That’s intrusive for a library (mutates global
  asyncio policy for the whole process). At minimum guard/document it; ideally
  leave loop-policy choices to the application.

---

## Prioritized action plan

| # | Item | Severity | Effort | Where |
|---|------|:--------:|:------:|-------|
| 1 | Fix `requires-python` (→ `>=3.11`/`3.13`) + drop the `assert` version guard | **Blocker** | XS | `pyproject.toml`, `package_descriptions.py` |
| 2 | Add offline unit tests (aioresponses) for intent-string + CSRF/token parsing + maintenance-recursion guard | High | M | `tests/` |
| 3 | Replace `MowerState` broken "stubs" with a real dataclass/TypedDict (or remove) + guard optional fields + protect `self.imow` | High | M | `mowerstate.py` |
| 4 | Fix maintenance-probe recursion (`_probe` flag) | High | S | `api/__init__.py` |
| 5 | Make `api_request` return parsed payloads; switch reads to `response.json()` | Medium | M | `api/__init__.py` |
| 6 | Correct error contracts: `ValueError` for bad args; `isinstance`; remove dead `except ConnectionError`; re-raise non-404 in `fetch_messages`; `IMowError` base | Medium | S–M | `api/__init__.py`, `exceptions.py` |
| 7 | Type hygiene: `Optional[...]`, drop `any`, fix `mower_id` default, `py.typed`, add mypy to CI | Medium | S–M | all |
| 8 | Timezone-aware datetimes for intent defaults + expiry | Medium | S | `api/__init__.py` |
| 9 | Move the ~1.6k-line message tables to a data file; dict-index lookups; fix short/long return | Medium | M | `messages.py` |
| 10 | `black`/`flake8` clean + docstring/typo pass; rename repo-root `secrets.py`; trim `close()` sleep; drop global loop-policy side effect | Low | S | all |
| 11 | Cross-repo: HA injects `async_create_clientsession`, persists token, stops forced reauth | Medium | S | `ha-stihl-imow` |

---

## What’s already good (keep it)

- Auth hardening: `asyncio.Lock` single-flight re-auth, cookie clearing with the
  correct **host** args, 401→re-auth-once-retry, typed `LoginError` with
  status/url diagnostics, OAuth `state` generation, backoff+jitter on transient
  GETs. This is the right shape and resolves the reported HA crash class.
- `_owns_session` — never closing a caller-injected session. Exactly right for HA.
- Injecting an external `aiohttp` session as the default usage pattern.
- Single-sourced version via hatch; clean `pyproject.toml` migration off
  `setup.py`.
- Clear separation of `actions` / `consts` / `exceptions` modules.

---

*Reviewed with the `python-expert` skill; aiohttp session/cookie/response-lifecycle
claims verified against aiohttp stable (3.13.x) docs via context7.*
