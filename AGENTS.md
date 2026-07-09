# AGENTS.md — stihl-imow-webapi

Unofficial **async** Python wrapper for the STIHL iMOW cloud WebAPI (RMI / Gen ≤4 mowers only). Published to PyPI as `imow-webapi`. Consumed by the sibling `ha-stihl-imow` Home Assistant integration in this workspace.

## Architecture
- `imow/api/__init__.py` — the `IMowApi` class is the entire client. It owns the `aiohttp.ClientSession`, auth/token lifecycle, and all HTTP calls. Everything funnels through `api_request(url, method, payload, headers)`, which injects browser-like headers, a `Bearer` token, auto-reauths when the token has <1 day left, and calls `check_api_maintenance()` on HTTP 500.
- Auth is a scraped OAuth flow: `__fetch_new_csrf_token_and_request_id()` uses BeautifulSoup to pull `csrf-token`/`requestId` from the login HTML, then `__authenticate()` posts form-encoded creds and extracts `access_token` from the redirect URL fragment via `furl`. Tokens last 30 days.
- `imow/common/mowerstate.py` — `MowerState` wraps an upstream dict. `replace_state()` does `self.__dict__.update(...)` so **every API field becomes a dynamic attribute** (declared as type-hint stubs at the bottom of the class for IDEs, not real defaults). Instances hold a back-reference to `IMowApi` (`self.imow`) to lazily fetch statistics/startpoints/settings.
- `imow/common/messages.py` — `Messages` resolves localized state/error text from STIHL's i18n JSON. `MowerState` always builds a language-neutral `machineState` (UPPER_SNAKE) from the English messages plus a localized `stateMessage` dict.
- `imow/common/actions.py` — `IMowActions` enum is the only valid action vocabulary: `EDGE_MOWING`, `TO_DOCKING`, `START_MOWING_FROM_POINT`, `START_MOWING`.
- `imow/common/consts.py` holds the two base URLs; `exceptions.py` defines `LoginError`, `ApiMaintenanceError`, `LanguageNotFoundError`.

## Conventions
- **Async-only.** Every public method is a coroutine; callers must `await`. Prefer passing in an external `aiohttp` session (`IMowApi(aiohttp_session=session)`); if none is given, `api_request` lazily creates one with `raise_for_status=True`.
- Actions are issued two ways — `api.intent(action, mower_name=...)` or `mower_state.intent(action)` (the latter fills `mower_external_id` from `self.externalId`). `intent()` translates `**kwargs` (`duration`, `startpoint`, `starttime`, `endtime`) into `first/second_action_value_param`; datetimes go through `validate_and_fix_datetime` (`"%Y-%m-%d %H:%M"`).
- `mower_external_id` must be exactly 16 chars — code asserts this. Use `get_mower_action_id_from_name/id` to resolve it.
- Logging: use `logging.getLogger("imow")`. Never log tokens/credentials (existing code redacts them).
- Version lives in `imow/common/package_descriptions.py` (`__version__`); `pyproject.toml` (hatchling) reads it dynamically via `[tool.hatch.version]`. Bump it there.

## Workflows
- Install dev: `uv sync --group dev` (runtime + dev deps declared in `pyproject.toml`; dev tools: pytest, pytest-asyncio, black, flake8, pdoc3). Run tools via `uv run <tool>`.
- Unit tests (offline, use a fake token): `pytest -s tests/test_unit*`.
- Integration tests hit the live STIHL API and need a repo-root `secrets.py` with `EMAIL`, `PASSWORD`, `MOWER_NAME`: `pytest -s tests/test_integration*`. Do not commit `secrets.py`.
- Format with `black` before committing; docs are generated with `pdoc3` into `docs/`.

## Gotchas
- Because `MowerState` attributes come from the upstream payload, referencing a field that STIHL didn't return raises `AttributeError` at access time — guard optional fields.
- Only Gen ≤4 mowers (app.imow.stihl.com) work; myimow.stihl.com accounts are unsupported by design (see issue #13).
