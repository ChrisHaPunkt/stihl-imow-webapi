# Changelog

## Version 0.10.0 (2026-07-09)
### Fixed
- Packaging: relax `requires-python` from `>=3.14` to `>=3.13` (3.14 made the
  package uninstallable on current Home Assistant stable, which targets 3.13).
  The runtime `aiohttp~=3.9` bound keeps working on both HA stable (aiohttp
  3.13.x) and HA dependency-next (aiohttp 3.14.x). Dropped the strippable
  `assert`-based version guard and the import-time global asyncio
  event-loop-policy side effect.
- Maintenance probe no longer risks infinite recursion: a 500 from the
  maintenance endpoint itself is not fed back into the maintenance check
  (new internal `_probe` guard).
- `MowerState` no longer crashes on partial payloads: a missing `status` block or
  an unknown state/error code degrades to `machineState = "UNKNOWN"` instead of
  raising. Upstream keys can no longer clobber the client back-reference
  (`imow`) or the derived message fields.
- `fetch_messages` re-raises non-404 HTTP errors instead of silently leaving the
  message tables unset.
- `get_status_by_id` / `get_mower_action_id_from_id` map a 404 to `LookupError`
  (the previous `except ConnectionError` was dead code and never fired).
- `get_status_message` now returns distinct short/long text (falling back to the
  short text when the language file has no long variant).
### Changed
- Added `receive_mower_state_with_statistics(mower_id)`: fetches a mower's
  state, paces the follow-up statistics request (avoiding upstream timeouts),
  and returns the state with `statistics` attached. Consumers no longer need to
  pace these two calls themselves.
- Type safety: added `Optional[...]` annotations throughout, replaced the builtin
  `any` used as an annotation with `typing.Any`, added a `py.typed` marker, and
  the package now type-checks clean under `mypy`.
- `MowerState`'s misleading "type stub" block (which assigned `set`/`None`
  objects as class defaults) is replaced with annotation-only field declarations
  that document the payload without creating runtime values.
- Read endpoints share a single `_request_json` helper and `response.json()`
  instead of hand-rolled `json.loads(await response.text())`; request headers
  are centralised in one `_default_headers()`.
- `intent()` value construction is extracted into tested pure helpers, validates
  unknown keyword arguments, enforces an exactly-16-char external id, raises
  `ValueError` (not `AttributeError`) for bad arguments, and returns `None` (not
  `True`) in `test_mode`.
- Token-expiry math uses timezone-aware UTC.
- Errors now share a common `IMowError` base class for easy broad handling.
- Added an offline unit-test suite (`aioresponses`) covering the intent-value
  builders, CSRF scraping and failure modes, token handling, the maintenance
  recursion guard, and session ownership; integration tests read credentials
  from `IMOW_*` env vars (falling back to a repo-root secrets file). The dev
  group pins `aiohttp<3.14` for tests only (aioresponses can't mock aiohttp 3.14
  yet — pnuckowski/aioresponses#289); this does not constrain the runtime.

## Version 0.9.0 (2026-07-09)
### Fixed
- Authentication robustness: isolate STIHL session cookies (fixes the login
  landing on the already-authenticated SPA shell, which raised a misleading
  `ProcessLookupError`). Logout now clears cookies by host correctly.
- Serialize (re)authentication with a lock and single-flight double-check so
  concurrent callers don't trigger parallel logins.
- Proactively refresh tokens with a known expiry and recover from a stale token
  via a one-shot 401 → re-auth → retry.
- Retry transient GET failures with bounded exponential backoff.
- `api_request` now buffers the response body correctly instead of returning a
  released response context.
### Changed
- Harden CSRF/requestId scraping: fall back to the `<meta>` tag, detect the SPA
  shell / maintenance page, and raise a typed `LoginError` with diagnostics.
- Generate a real random OAuth `state`; only close aiohttp sessions the library
  created itself (never a caller-injected one).
- Packaging moved to `pyproject.toml` (PEP 621) with the hatchling build backend
  and `uv` for builds/dev environments; `setup.py` removed.

## Version 0.8.4 (2023-12-09)
### Fix
- Loosen the version requirements for dependency libs
- update the tested python version placed inside setup and PyPi to python 3.12

## Version 0.8.2 (2023-08-26)
### Fix
- validation of values in keyword arguments
### BREAKING CHANGE
The iMow action `IMowActions.START_MOWING` now creates a `startMowing` action and no longer a `startMowingFromPoint` action.
To issue a `startMowingFromPoint`, the new `IMowAction.START_MOWING_FROM_POINT` needs to be used.

#### Added 
- keywork arguments `starttime` and `endtime` in `IMow.intent()` call to be used with IMowActions.START_MOWING
- Updated Readme with `IMow.intent` exampes
- added debug log output in `intent()` call

## Version 0.7.10 (2023-05-13)
- Bugfix http_session not present on logout
## Version 0.7.9 (2023-05-13)
- remove unnecessary http_session closes
## Version 0.7.8 (2022-03-06)
- Implement a logout function `ImowAPI.api_logout()`. Use within re-authentication
## Version 0.7.7 (2022-03-06)
- Use more `async with`s
## Version 0.7.6 (2022-03-05)

### Dependency updates
- Update dependencies to latest

## Version 0.7.4 (2021-09-06)

### Bugfxes
- Allow handling of timestamps on mower intents (StartTime/Endtime)

## Version 0.7.3 (2021-07-03)

### Bugfxes
- Always return a MowerState on settings update

## Version 0.7.2 (2021-07-03)
```python
await mower.update_setting("gpsProtectionEnabled", True)
```
### Features
- Possibility to update a specific settings for a mower like gpsProtection on/off
## Version 0.7.0 (2021-06-30)
### Breaking Changes
- `IMowApi.intent` Parameter `mower_action_id` is renamed to `mower_external_id` to match the upstream api expectation.
### Features
- If an `api_request` is intended, and the used `access_token` expires in less than one day, it's automatically renewed.

## Version 0.6.0 (2021-06-28)
- ```python
  mower.machineError = 'M1120',
  mower.machineState = 'HOOD_BLOCKED',
  mower.stateMessage: dict = {
      'short': 'Hood blocked',
      'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).',
      'legacyMessage': 'Abschaltung Automatikmode durch Bumper',
      'errorId': 'M1120',
      'error': True
  }
  ```

### Breaking Changes
- Migrated all own MowerState attributes to camelCase to match the upstream attributes style.
  ```
  - MowerState.stateMessage = None
  - MowerState.machineError = None
  - MowerState.machineState = None
  ```
## Version 0.5.2 (2021-06-15)

## Bugfixes
- Also quote password string in auth request to support more special chars

## Version 0.5.1 (2021-06-13)

## Features
- ```python
  mower.machine_error = 'M1120',
  mower.machine_state = 'HOOD_BLOCKED',
  mower.state_message: dict = {
      'short': 'Hood blocked',
      'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).',
      'legacyMessage': 'Abschaltung Automatikmode durch Bumper',
      'errorId': 'M1120',
      'error': True
  }
  ```
  Provide a machine usable string from the short message in english

## Version 0.5.0 (2021-06-12)

### Breaking Changes

- The ``MowerTask`` class is removed in favor of the new ``state_message`` property on th ``MowerState`` object.
- The ``MowerState.get_current_task()`` method now returns the `short` property of the state message instead of a ``MowerTask``
  property and is now longer an ``async`` method.

### Features

- ```python
  mower.state_message -> dict
  {
      'short': 'Hood blocked',
      'long': 'The hood is blocked. Please check the hood and press the OK button on your machine (M1120).',
      'errorId': 'M1120',
      'error': True
  }
  ```
  The MowerState Class now provides a ```state_message``` property which gives a ``short`` and``long`` text for
  description (Besides an error indication and errorId). All error and status codes are now dynamically matched and
  human readable available.
  **This makes the ``MowerTask`` obsolete and it is removed with this release.**
- ``api = IMowApi(lang="en")``
  The imow api can now be instanced with a language code (fallback to ``en``).
  The ``state_message`` property displays the messages in the corresponding language.

## Version 0.4.5 (2021-06-01)

### Features

- Add 2 new identified Tasks within `MowerTask` (Thanks to @lausser)
- Add `check_api_maintenance()` method to `IMowAPI` Class. Check if the api server is currently under maintenance.
  This method is automatically called if the api server returns a 500 error response for any request.
- One should call the new `close()` method for the `IMowAPI` Class when finishing the api interactions to correctly
  close the http session.

### Bugfixes

- [Issue #8](https://github.com/ChrisHaPunkt/stihl-imow-webapi/issues/8) - Example not working

## Version 0.4.4 (2021-05-28)

### Features

- Add `validate_token()` method to `IMowAPI` Class. Test if a token is valid and is able to call the webapi.

## Version 0.4.3 (2021-05-27)

### Features

- Allow `IMowAPI` Class to use predefined `aiohttp` session when instantiating

## Version 0.4.1 (2021-05-24)

### Changes

- Even more asynchronously with switch from `requests` to `aiohttp`

## Version 0.4.0 (2021-05-17)

### Breaking Changes

- Reworked everything to use asyncio where possible. See Readme.md for new usage example.
- Renamed MowerState method `update` to `update_from_upstream`
- Renamed MowerState method `get_status` to `get_current_status`

## Version 0.3.0 (2021-05-17)

### Breaking Changes

- Renamed Class/Enum `MowerState` to `MowerTask` because it describes the current task not the state
- Renamed Class `Mower` to `MowerState` because it's just a snapshot of the last upstream state

### Features

- Add methods to work on `MowerState` objects, like action intents or statistic receive
- Add PDoc documents, available
  on [https://chrishapunkt.github.io/stihl-imow-webapi/imow](https://chrishapunkt.github.io/stihl-imow-webapi/imow)

### Bugfixes

- Return a valid error message and raise if provided login credentials are wrong

## Version 0.2.2 (2021-05-00)

- Initial release
