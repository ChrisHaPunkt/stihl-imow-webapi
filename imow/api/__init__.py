from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple, Union
from urllib.parse import quote

import aiohttp
from aiohttp import ClientSession, ClientResponseError, ClientResponse
from bs4 import BeautifulSoup
from furl import furl

from imow.common.actions import IMowActions
from imow.common.consts import (
    IMOW_OAUTH_URI,
    IMOW_API_URI,
    IMOW_APP_URI,
    IMOW_OAUTH_CLIENT_ID,
    IMOW_COOKIE_HOSTS,
    IMOW_MAINTENANCE_URI,
    IMOW_USER_API_URI,
    IMOW_I18N_BASE_URI,
)
from imow.common.exceptions import (
    LoginError,
    ApiMaintenanceError,
    LanguageNotFoundError,
)
from imow.common.messages import Messages
from imow.common.mowerstate import MowerState

logger = logging.getLogger("imow")


def validate_and_fix_datetime(value: str) -> str:
    """Validate and normalise a datetime string to ``"%Y-%m-%d %H:%M"``.

    Accepts either ``"%Y-%m-%d %H:%M"`` or ``"%Y-%m-%d %H:%M:%S"`` and returns
    the value formatted as ``"%Y-%m-%d %H:%M"``.

    Args:
        value: The datetime string to check.

    Returns:
        The correctly formatted datetime string.

    Raises:
        ValueError: If ``value`` matches neither supported format.
    """
    try:
        datetime_object = datetime.strptime(value, "%Y-%m-%d %H:%M")
        return datetime_object.strftime("%Y-%m-%d %H:%M")
    except ValueError as ve:
        logger.warning(f"  Try fixing given time format because {ve} in {value}")
        try:
            datetime_object = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return datetime_object.strftime("%Y-%m-%d %H:%M")
        except ValueError as ve2:
            raise ValueError(f'Unsupported "time" argument: {value} -> {ve2}')


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``.

    Timezone-aware UTC avoids DST edge cases in token-expiry math and keeps
    comparisons correct regardless of the host machine's local timezone.
    """
    return datetime.now(timezone.utc)


def _extract_attr(element, attr: str) -> Optional[str]:
    """Return a single string attribute from a BeautifulSoup element, or None.

    Handles the ``None`` (not found), ``NavigableString`` (no attributes) and
    multi-valued attribute cases so callers get a plain ``str`` or ``None``.
    """
    getter = getattr(element, "get", None)
    if getter is None:
        return None
    value = getter(attr)
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value) or None
    return str(value)


# Valid keyword names accepted by ``IMowApi.intent`` for value translation.
_INTENT_KWARGS = frozenset({"duration", "startpoint", "starttime", "endtime"})


def _build_start_from_point_value(
    mower_external_id: str,
    duration: Any = "",
    startpoint: Any = "",
) -> str:
    """Build the ``actionValue`` for ``START_MOWING_FROM_POINT``.

    Format: ``"<extId>,<durationMinutes/10>,<startpoint>"``. Duration defaults
    to 30 minutes, startpoint to ``0``.
    """
    duration_value = str(int(duration) / 10) if duration else str(30 / 10)
    startpoint_value = str(startpoint) if startpoint else "0"
    return f"{mower_external_id},{duration_value},{startpoint_value}"


def _build_start_mowing_value(
    mower_external_id: str,
    endtime: Any = "",
    starttime: Any = "",
) -> str:
    """Build the ``actionValue`` for ``START_MOWING``.

    Format: ``"<extId>,<endtime>[,<starttime>]"``. Applies defaults:
    - only ``starttime`` given → end 2h after start;
    - neither given → end 2h from now (local time).

    Raises:
        ValueError: If ``endtime`` is not strictly after ``starttime``.
    """
    endtime = str(endtime) if endtime != "" else None
    starttime = str(starttime) if starttime != "" else None

    if starttime and not endtime:
        endtime = (
            datetime.strptime(starttime, "%Y-%m-%d %H:%M") + timedelta(hours=2)
        ).strftime("%Y-%m-%d %H:%M")
    elif not starttime and not endtime:
        now = datetime.now()
        logger.warning(
            "No start- or endtime is given. Creating an action object with "
            "endtime 2 hours from now based on this machine's local timezone. "
            "datetime.now() gives %s.",
            now.strftime("%Y-%m-%d %H:%M"),
        )
        endtime = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")

    if starttime:
        if datetime.strptime(starttime, "%Y-%m-%d %H:%M") < datetime.strptime(
            endtime, "%Y-%m-%d %H:%M"
        ):
            return f"{mower_external_id},{endtime},{starttime}"
        raise ValueError(
            f"End time {endtime} is not after start time {starttime}. "
            "Time travel is not supported."
        )
    return f"{mower_external_id},{endtime}"


class IMowApi:
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        aiohttp_session: Optional[ClientSession] = None,
        lang: str = "en",
    ) -> None:
        self.http_session: Optional[ClientSession] = aiohttp_session
        self.csrf_token: str = ""
        self.requestId: str = ""
        self.access_token: Optional[str] = token
        self.token_expires: Optional[datetime] = None
        self.api_email: Optional[str] = email
        self.api_password: Optional[str] = password
        self.lang: str = lang
        self.messages_user: Optional[Messages] = None
        self.messages_en: Optional[Messages] = None
        # Only close sessions we created ourselves; never a caller-injected one.
        self._owns_session: bool = aiohttp_session is None
        # Serialize (re)authentication so concurrent callers don't trigger
        # parallel logins that race on csrf_token/access_token.
        self._auth_lock: asyncio.Lock = asyncio.Lock()
        # Per-login OAuth state (CSRF protection for the redirect).
        self._oauth_state: str = ""

    # Number of days before expiry at which we proactively re-authenticate.
    _TOKEN_REFRESH_LEEWAY_SECONDS = 86400

    # Pause between the mower-state and statistics requests. Issuing them
    # back-to-back can trigger upstream timeouts, so callers that need both
    # should use ``receive_mower_state_with_statistics`` rather than pacing
    # the two calls themselves.
    _STATISTICS_FETCH_DELAY_SECONDS = 1

    async def close(self):
        """Cleanup the aiohttp Session.

        Only closes the session if this instance created it. A caller-injected
        session (e.g. Home Assistant's shared/created client session) is owned by
        the caller and must not be closed here.
        """
        if self._owns_session and self.http_session and not self.http_session.closed:
            await self.http_session.close()

    def _ensure_session(self) -> ClientSession:
        """Make sure we have a usable aiohttp session, creating an owned one.

        Returns the (now guaranteed non-None) session for convenient narrowing.
        """
        if not self.http_session or self.http_session.closed:
            self.http_session = aiohttp.ClientSession(raise_for_status=True)
            self._owns_session = True
        return self.http_session

    def _clear_stihl_cookies(self) -> None:
        """Clear STIHL auth/session cookies from the active jar.

        Prevents a stale session cookie from redirecting the login GET to the
        already-authenticated SPA shell (which lacks the csrf-token/requestId
        inputs). Works whether the session is owned or injected.
        """
        if not self.http_session or self.http_session.closed:
            return
        jar = self.http_session.cookie_jar
        clear_domain = getattr(jar, "clear_domain", None)
        if clear_domain is None:
            jar.clear()
            return
        for host in IMOW_COOKIE_HOSTS:
            clear_domain(host)

    def _token_needs_refresh(self) -> bool:
        """Whether the current token should be proactively re-authenticated.

        Unknown expiry (``token_expires is None``) returns ``False`` so we don't
        needlessly re-login for injected tokens; a stale token is handled via the
        401 retry path in ``api_request`` instead.
        """
        if not self.access_token:
            return True
        if self.token_expires is None:
            return False
        remaining = (self.token_expires - _utcnow()).total_seconds()
        return remaining <= self._TOKEN_REFRESH_LEEWAY_SECONDS

    async def check_api_maintenance(self) -> None:
        """Probe the maintenance endpoint and raise if the API is unavailable.

        The probe passes ``_probe=True`` so that a 500 from the maintenance
        endpoint itself does not recurse back into ``check_api_maintenance``.

        Raises:
            ApiMaintenanceError: If the upstream reports a disruption/outage.
        """
        headers = {
            "Authorization": "",
        }
        status = await self._request_json(
            IMOW_MAINTENANCE_URI,
            "GET",
            headers=headers,
            authenticated=False,
            _probe=True,
        )
        logger.debug(status)
        if status["serverDisrupted"] or status["serverDown"]:
            msg = (
                f"iMow API is under Maintenance -> "
                f'serverDisrupted: {status["serverDisrupted"]}, '
                f'serverDown: {status["serverDown"]}, '
                f'affectedTill {status["affectedTill"]}'
            )
            raise ApiMaintenanceError(msg)

    async def get_token(
        self,
        email: str = "",
        password: str = "",
        force_reauth: bool = False,
        return_expire_time: bool = False,
    ) -> Union[Tuple[str, Optional[datetime]], str]:
        """
        look for a token, if present, return. Else authenticate and store new token
        :param return_expire_time:
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :param force_reauth: Force a re-authentication with username and password
        :return: the access token and a datetime object containing the expiry
        """

        if email and password:
            self.api_password = password
            self.api_email = email

        # Capture the token before waiting on the lock so we can detect whether
        # another coroutine already (re)authenticated while we were queued.
        token_before = self.access_token

        async with self._auth_lock:
            another_refresh_happened = (
                force_reauth and self.access_token and self.access_token != token_before
            )
            need_auth = (
                not self.access_token
                or (force_reauth and not another_refresh_happened)
                or self._token_needs_refresh()
            )

            if need_auth:
                if force_reauth:
                    await self.api_logout()
                    self.csrf_token = ""
                    self.requestId = ""
                    self.access_token = ""
                    self.token_expires = None
                if not self.api_email or not self.api_password:
                    raise LoginError(
                        "Got no credentials to authenticate, please provide"
                    )
                logger.debug("Get Token: (re-)authenticating")
                await self.__authenticate(self.api_email, self.api_password)

        token = self.access_token or ""
        if return_expire_time:
            return token, self.token_expires
        return token

    async def api_logout(self) -> None:
        """Best-effort logout: POST the logout form (if a CSRF token is known)
        and clear STIHL cookies from the jar.

        ``clear_domain`` (called via ``_clear_stihl_cookies``) expects a host,
        not a URL.
        """
        session = self._ensure_session()
        if self.csrf_token:
            async with session.post(
                f"{IMOW_OAUTH_URI}/authentication/logout/",
                data={
                    "csrf-token": self.csrf_token,
                    "logoutUrl": IMOW_APP_URI,
                    "clientId": IMOW_OAUTH_CLIENT_ID,
                    "cancelUrl": IMOW_APP_URI,
                },
            ) as resp:
                await resp.read()
        self._clear_stihl_cookies()

    async def validate_token(self, explicit_token: Optional[str] = None) -> bool:
        """Validate a token by performing an authenticated request.

        Note:
            When ``explicit_token`` is given, the instance token is temporarily
            swapped for the duration of the check. This is **not** safe to call
            concurrently with other authenticated requests on the same instance;
            it is intended for one-off validation (e.g. from a config flow).

        Args:
            explicit_token: A token to validate instead of the instance token.

        Returns:
            ``True`` if the request succeeded.

        Raises:
            aiohttp.ClientResponseError: If the token is rejected upstream.
        """
        old_token = None
        if explicit_token:
            # save old instance token and place temp token for validation
            old_token = self.access_token
            self.access_token = explicit_token
        try:
            await self.receive_mowers()
        finally:
            if explicit_token:
                # Reset instance token even if validation raised.
                self.access_token = old_token
        return True

    async def __authenticate(
        self, email: str, password: str
    ) -> Tuple[str, datetime, ClientResponse]:
        """
        try the authentication request with fetched csrf and requestId payload
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :return: the new access token, expiry, and the raw response
        """

        await self.__fetch_new_csrf_token_and_request_id()
        url = f"{IMOW_OAUTH_URI}/authentication/authenticate/?lang={self.lang}"
        payload = {
            "mail": email,
            "password": password,
            "csrf-token": self.csrf_token,
            "requestId": self.requestId,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        response = await self.api_request(
            url, "POST", payload=payload, headers=headers, authenticated=False
        )

        response_url_query_args = furl(response.real_url).fragment.args
        if "access_token" not in response_url_query_args:
            raise LoginError(
                "STIHL iMow did not return an access_token, check your credentials"
            )

        self.access_token = response_url_query_args["access_token"]
        self.token_expires = _utcnow() + timedelta(
            seconds=int(response_url_query_args["expires_in"])
        )
        return self.access_token, self.token_expires, response

    async def __fetch_new_csrf_token_and_request_id(
        self,
    ) -> Tuple[str, str]:
        """
        Fetch a new csrf_token and requestId to authenticate as expected by the api.
        csrf_token and requestId are used as payload within authentication
        """

        # Start each login from a clean cookie state so we always land on the
        # login form and never on the already-authenticated SPA shell.
        self._clear_stihl_cookies()

        # Generate a fresh OAuth state (CSRF protection for the redirect).
        # os.urandom (not the stdlib ``secrets`` module) is used deliberately to
        # avoid clashing with a repo-root ``secrets.py`` on the import path.
        self._oauth_state = (
            base64.urlsafe_b64encode(os.urandom(30)).rstrip(b"=").decode()
        )
        authorization_redirect = (
            f"{IMOW_OAUTH_URI}/authorization/"
            f"?response_type=token"
            f"&client_id={IMOW_OAUTH_CLIENT_ID}"
            f"&redirect_uri={quote(f'{IMOW_APP_URI}/#/authorize', safe='')}"
            f"&state={self._oauth_state}"
        )
        url = (
            f"{IMOW_OAUTH_URI}/authentication/"
            f"?lang=de_DE"
            f"&authorizationRedirectUrl={quote(authorization_redirect, safe='')}"
        )
        response = await self.api_request(url, "GET", authenticated=False)

        html = await response.text()

        # Diagnostic: log which backend framework serves the login page.
        # Helps identify the upstream stack (e.g. Microsoft-IIS/ASP.NET, Express,
        # PHP) without guessing, and surfaces when we land on an unexpected page.
        logger.debug(
            "Auth login page served by: status=%s, final_url=%s, "
            "Server=%r, X-Powered-By=%r, Content-Type=%r",
            response.status,
            str(response.real_url),
            response.headers.get("Server"),
            response.headers.get("X-Powered-By"),
            response.headers.get("Content-Type"),
        )

        soup = BeautifulSoup(html, "html.parser")

        upstream_csrf_token = _extract_attr(
            soup.find("input", {"name": "csrf-token"}), "value"
        )
        if not upstream_csrf_token:
            # Fall back to the <meta name="csrf-token"> tag if the hidden input
            # is missing (e.g. markup change).
            upstream_csrf_token = _extract_attr(
                soup.find("meta", {"name": "csrf-token"}), "content"
            )
        upstream_request_id = _extract_attr(
            soup.find("input", {"name": "requestId"}), "value"
        )

        if not upstream_csrf_token or not upstream_request_id:
            # Distinguish the common failure modes for a clear, actionable error.
            if soup.find("stihl-imow-root") is not None:
                detail = (
                    "landed on the already-authenticated SPA shell instead of "
                    "the login form (stale session cookies)"
                )
            elif "maintenance" in html.lower():
                detail = "the upstream appears to be under maintenance"
            else:
                detail = "the login form did not contain the expected fields"
            raise LoginError(
                "Could not obtain csrf-token/requestId from the STIHL login "
                f"page: {detail} "
                f"(status={response.status}, url={response.real_url})."
            )

        self.csrf_token = upstream_csrf_token
        self.requestId = upstream_request_id
        logger.debug("CSRF: new token and request id <redacted>")
        return self.csrf_token, self.requestId

    async def fetch_messages(self) -> None:
        """Download and cache the i18n message tables from the SPA.

        Fetches the English tables (used for the language-neutral
        ``machineState``) and, when ``self.lang != "en"``, the localized tables.

        Raises:
            LanguageNotFoundError: If the requested language file does not exist.
            aiohttp.ClientResponseError: For any other HTTP error.
        """
        session = self._ensure_session()
        try:
            url_en = f"{IMOW_I18N_BASE_URI}/en.json"
            async with session.request("GET", url_en) as response_en:
                i18n_en = await response_en.json(content_type=None)
            self.messages_en = Messages(i18n_en)
            if self.lang != "en":
                url_user = f"{IMOW_I18N_BASE_URI}/{self.lang}.json"
                async with session.request("GET", url_user) as response_user:
                    i18n_user = await response_user.json(content_type=None)
                    self.messages_user = Messages(i18n_user)
            else:
                self.messages_user = self.messages_en

        except ClientResponseError as e:
            if e.status == 404:
                raise LanguageNotFoundError(
                    f"Language-File '{self.lang}.json' not found on imow upstream "
                    f"({IMOW_I18N_BASE_URI}/{self.lang}.json)"
                ) from e
            # Any other HTTP error must not be swallowed: leaving messages_en
            # unset would break state-message resolution on the next call.
            raise

    def _default_headers(self) -> dict:
        """Browser-like default headers sent with every API request.

        A single source of truth so the (spoofed) User-Agent and related headers
        don't drift between call sites.
        """
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) "
                "Gecko/20100101 Firefox/88.0"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
            "Authorization": f'Bearer {self.access_token or ""}',
            "Origin": IMOW_APP_URI,
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": f"{IMOW_APP_URI}/",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "Trailers",
            "Content-Type": "application/json",
        }

    async def _request_json(
        self,
        url,
        method,
        payload=None,
        headers=None,
        authenticated: bool = True,
        _probe: bool = False,
    ) -> Any:
        """Perform a request via :meth:`api_request` and return parsed JSON.

        Convenience wrapper used by all read endpoints so callers don't hand-roll
        ``json.loads(await response.text())``.
        """
        response = await self.api_request(
            url,
            method,
            payload=payload,
            headers=headers,
            authenticated=authenticated,
            _probe=_probe,
        )
        return await response.json(content_type=None)

    async def api_request(
        self,
        url,
        method,
        payload=None,
        headers=None,
        authenticated: bool = True,
        _is_retry: bool = False,
        _probe: bool = False,
    ) -> aiohttp.ClientResponse:
        """
        Do a standardized request against the stihl imow webapi, with predefined
        headers.

        The returned response has already had its body buffered
        (``await response.read()``), so ``response.text()`` / ``response.json()``
        / ``response.status`` remain usable after the connection is released back
        to the pool. Prefer :meth:`_request_json` for read endpoints.

        :param url: The target URL
        :param method: The Method to use
        :param payload: optional payload (dict → form-encoded, str/bytes → raw)
        :param headers: optional update headers
        :param authenticated: whether this request needs a valid bearer token.
            Set to ``False`` for the auth handshake and maintenance probe to avoid
            recursive re-authentication / lock re-entrancy.
        :param _is_retry: internal flag to prevent infinite 401 re-auth loops.
        :param _probe: internal flag for the maintenance probe; prevents a 500
            from the maintenance endpoint recursing back into the maintenance
            check. Non-GET requests are issued single-shot (not retried).
        :return: the aiohttp.ClientResponse (body already buffered)
        """
        session = self._ensure_session()
        if not self.messages_en:
            await self.fetch_messages()

        if authenticated:
            if not self.access_token and (self.api_email and self.api_password):
                # No token yet but we can obtain one.
                await self.get_token()
            elif self.token_expires and self._token_needs_refresh():
                logger.info("Fetching new access_token because old one expires soon")
                await self.get_token(force_reauth=True)

        if not payload:
            payload = {}

        headers_obj = self._default_headers()
        if headers:
            headers_obj.update(headers)

        max_attempts = 3 if method == "GET" else 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = await session.request(
                    method, url, headers=headers_obj, data=payload
                )
                # Buffer the body so the response stays usable after the
                # connection is released back to the pool.
                await response.read()
                response.raise_for_status()
                return response
            except ClientResponseError as e:
                if (
                    authenticated
                    and e.status == 401
                    and not _is_retry
                    and (self.api_email and self.api_password)
                ):
                    logger.info("Got HTTP 401, re-authenticating once and retrying")
                    await self.get_token(force_reauth=True)
                    return await self.api_request(
                        url,
                        method,
                        payload=payload,
                        headers=headers,
                        authenticated=authenticated,
                        _is_retry=True,
                        _probe=_probe,
                    )
                # Don't recurse into the maintenance check from the probe itself.
                if e.status == 500 and not _probe:
                    await self.check_api_maintenance()
                raise e
            except (
                aiohttp.ClientConnectionError,
                asyncio.TimeoutError,
            ) as e:
                if attempt >= max_attempts:
                    raise e
                backoff = 0.5 * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                logger.debug(
                    "Transient error on %s %s (attempt %s/%s): %s; retrying in %.2fs",
                    method,
                    url,
                    attempt,
                    max_attempts,
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)

        # Unreachable: the loop either returns or raises on the final attempt.
        raise RuntimeError("api_request exhausted retries without returning")

    async def intent(
        self,
        imow_action: IMowActions,
        mower_name: str = "",
        mower_id: str = "",
        mower_external_id: str = "",
        first_action_value_param: Any = "",
        second_action_value_param: Any = "",
        test_mode: bool = False,
        **kwargs,
    ) -> Optional[aiohttp.ClientResponse]:
        """Issue a mower action ("intent"), creating a job object upstream.

        The action object carries an action name and an ``actionValue``. For
        most actions the value is just ``<MowerExternalId>``; for
        ``START_MOWING_FROM_POINT`` it is
        ``<MowerExternalId,DurationInMinutes/10,StartPoint>`` and for
        ``START_MOWING`` it is ``<MowerExternalId,EndTime[,StartTime]>``.

        Args:
            imow_action: One of :class:`~imow.common.actions.IMowActions`.
            mower_name: Identify the mower by name (looked up to an external id).
            mower_id: Identify the mower by numeric id (looked up to an
                external id).
            mower_external_id: The 16-char external id used for actions. Looked
                up automatically when only ``mower_name``/``mower_id`` is given.
            first_action_value_param: For ``START_MOWING_FROM_POINT`` a duration
                in minutes (default 30); for ``START_MOWING`` an end time
                (``"%Y-%m-%d %H:%M"``).
            second_action_value_param: For ``START_MOWING_FROM_POINT`` a start
                point (default 0); for ``START_MOWING`` a start time.
            test_mode: If ``True``, do not send the request; returns ``None``.
            **kwargs: Optional ``duration``/``startpoint``/``starttime``/
                ``endtime`` that map onto the value params above.

        Returns:
            The :class:`aiohttp.ClientResponse`, or ``None`` in ``test_mode``.

        Raises:
            ValueError: For an invalid mower id or an unknown keyword argument.
        """
        if test_mode:
            logger.warning("TEST_MODE: Request will not be issued to server.")
        if not mower_external_id and not mower_id and not mower_name:
            raise ValueError(
                "Need some mower to work on. Please specify mower_[name|id|external_id]"
            )
        if not mower_external_id and mower_name:
            mower_external_id = await self.get_mower_action_id_from_name(mower_name)
        if not mower_external_id and mower_id:
            mower_external_id = await self.get_mower_action_id_from_id(mower_id)

        if len(mower_external_id) != 16:
            raise ValueError(
                "Invalid mower_external_id, need exactly 16 chars, "
                f"got {len(mower_external_id)} in {mower_external_id!r}"
            )

        url = f"{IMOW_API_URI}/mower-actions/"

        unknown_kwargs = set(kwargs) - _INTENT_KWARGS
        if unknown_kwargs:
            raise ValueError(
                f"Unknown intent keyword argument(s): {sorted(unknown_kwargs)}. "
                f"Valid keys are {sorted(_INTENT_KWARGS)}."
            )
        if kwargs:
            logger.debug("Translating given intent **kwargs to action_value_param")
            for key, value in kwargs.items():
                logger.debug("  %s = %s", key, value)
                if key == "duration" and value:
                    first_action_value_param = value
                if key == "startpoint" and value:
                    second_action_value_param = value
                if key == "endtime" and value:
                    first_action_value_param = validate_and_fix_datetime(value)
                if key == "starttime" and value:
                    second_action_value_param = validate_and_fix_datetime(value)

            logger.debug(
                "  -> first_action_value_param (end-time / duration): %s",
                first_action_value_param,
            )
            logger.debug(
                "  -> second_action_value_param (start-time / startpoint): %s",
                second_action_value_param,
            )

        logger.debug(
            'Build action object for: %s -> "%s"', imow_action, imow_action.value
        )
        # Build the action value depending on the given ACTION.
        if imow_action == IMowActions.START_MOWING_FROM_POINT:
            action_value = _build_start_from_point_value(
                mower_external_id,
                duration=first_action_value_param,
                startpoint=second_action_value_param,
            )
        elif imow_action == IMowActions.START_MOWING:
            action_value = _build_start_mowing_value(
                mower_external_id,
                endtime=first_action_value_param,
                starttime=second_action_value_param,
            )
        else:
            action_value = mower_external_id

        action_object = {
            "actionName": imow_action.value,
            "actionValue": action_value,
            # actionValue formats:
            #   "<MowerExternalId>,<DurationInMinutes/10>,<StartPoint>"
            #   "<MowerExternalId>,<EndTime>,<StartTime>"
        }
        logger.debug(
            "Intent sent as request body to imow api for mower with identifier: "
            "'%s/%s/%s'",
            mower_name,
            mower_id,
            mower_external_id,
        )
        logger.info("  %s", action_object)

        payload = json.dumps(action_object)

        if test_mode:
            logger.warning(
                "TEST_MODE: (NOT) Created mower (extId:%s) ActionObject with contents:",
                mower_external_id,
            )
            logger.warning("  %s", action_object)
            return None

        response = await self.api_request(url, "POST", payload=payload)
        if response.ok:
            logger.debug(
                "Success: Created mower (extId:%s) ActionObject with contents:",
                mower_external_id,
            )
            logger.debug(" %s", action_object)
            logger.debug(" -> (HTTP Status %s)", response.status)
        else:
            logger.error("No success with mower-action: %s", payload)
        return response

    async def update_setting(
        self, mower_id: Union[str, int], setting: str, new_value: Any
    ) -> MowerState:
        """Update a single mower setting via a PUT and return the fresh state.

        Args:
            mower_id: The mower's numeric id.
            setting: The settings key to change (must be a known field).
            new_value: The new value for ``setting``.

        Returns:
            The updated :class:`MowerState`.

        Raises:
            KeyError: If ``setting`` is not a known settings field.
        """
        mower_state = await self.receive_mower_by_id(mower_id)

        payload_fields = {
            "id": mower_state.id,
            "unitFormat": mower_state.unitFormat,
            "name": mower_state.name,
            "teamable": mower_state.teamable,
            "accountId": mower_state.accountId,
            "childLock": mower_state.childLock,
            "corridorMode": mower_state.corridorMode,
            "mappingIntelligentHomeDrive": mower_state.mappingIntelligentHomeDrive,
            "rainSensorMode": mower_state.rainSensorMode,
            "edgeMowingMode": mower_state.edgeMowingMode,
            "asmEnabled": mower_state.asmEnabled,
            "gpsProtectionEnabled": mower_state.gpsProtectionEnabled,
            "automaticModeEnabled": mower_state.automaticModeEnabled,
            "localTimezoneOffset": mower_state.localTimezoneOffset,
            "mowingTimeManual": None,
            "mowingTime": None,
            "team": mower_state.team,
            "timeZone": mower_state.timeZone,
        }
        if setting not in payload_fields:
            raise KeyError(
                f"Unknown setting {setting!r}. Known settings: "
                f"{sorted(payload_fields)}"
            )
        if payload_fields[setting] != new_value:
            payload_fields[setting] = new_value
            updated = await self._request_json(
                url=f"{IMOW_API_URI}/mowers/{mower_state.id}/",
                method="PUT",
                payload=json.dumps(payload_fields, indent=2).encode("utf-8"),
            )
            mower_state.replace_state(updated)
            return mower_state

        logger.info("%s is already %s.", setting, new_value)
        return await self.receive_mower_by_id(mower_id)

    async def get_status_by_name(self, mower_name: str) -> dict:
        logger.debug("get_status_by_name: %s", mower_name)
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.status
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def get_status_by_id(self, mower_id: Union[str, int]) -> dict:
        if not isinstance(mower_id, str):
            mower_id = str(mower_id)
        logger.debug("get_status_by_id: %s", mower_id)
        try:
            response = await self.receive_mower_by_id(mower_id)
            return response.status
        except ClientResponseError as e:
            if e.status == 404:
                raise LookupError(
                    f"Mower with id {mower_id} not found in upstream"
                ) from e
            raise

    async def get_status_by_action_id(self, mower_action_id: str) -> dict:
        logger.debug("get_status_by_action_id: %s", mower_action_id)
        for mower in await self.receive_mowers():
            if mower.externalId == mower_action_id:
                return mower.status
        raise LookupError(
            f"Mower with externalId {mower_action_id} not found in upstream"
        )

    async def get_mower_action_id_from_name(self, mower_name: str) -> str:
        logger.debug("get_mower_action_id_from_name: %s", mower_name)
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.externalId
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def get_mower_action_id_from_id(self, mower_id: Union[str, int]) -> str:
        logger.debug("get_mower_action_id_from_id: %s", mower_id)
        try:
            response = await self.receive_mower_by_id(mower_id)
            logger.debug(" - %s", response.externalId)
            return response.externalId
        except ClientResponseError as e:
            if e.status == 404:
                raise LookupError(
                    f"Mower with id {mower_id} not found in upstream"
                ) from e
            raise

    async def get_mower_id_from_name(self, mower_name: str) -> str:
        logger.debug("get_mower_id_from_name: %s", mower_name)
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.id
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def receive_mowers(self) -> List[MowerState]:
        logger.debug("receive_mowers: ")
        payload = await self._request_json(f"{IMOW_API_URI}/mowers/", "GET")
        mowers = [MowerState(mower, self) for mower in payload]
        for mower in mowers:
            logger.debug("  - %s", mower.name)
        return mowers

    async def receive_account(self) -> dict:
        """Return the authenticated user's account/profile.

        Mirrors the app's ``GET /me/`` call. The returned ``id`` is the stable
        STIHL account identifier and does not change when the account e-mail
        address changes, which makes it a good key for consumers that need a
        durable account reference.
        """
        logger.debug("receive_account: ")
        return await self._request_json(f"{IMOW_USER_API_URI}/me/", "GET")

    async def receive_mower_by_name(self, mower_name: str) -> MowerState:
        logger.debug("get_mower_from_name: %s", mower_name)
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                logger.debug(mower)
                return mower
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def receive_mower_by_id(self, mower_id: Union[str, int]) -> MowerState:
        logger.debug("receive_mower: %s", mower_id)
        payload = await self._request_json(f"{IMOW_API_URI}/mowers/{mower_id}/", "GET")
        mower = MowerState(payload, self)
        logger.debug(mower)
        return mower

    async def receive_mower_statistics(self, mower_id: Union[str, int]) -> dict:
        logger.debug("receive_mower_statistics: %s", mower_id)
        stats = await self._request_json(
            f"{IMOW_API_URI}/mowers/{mower_id}/statistic/", "GET"
        )
        logger.debug(stats)
        return stats

    async def receive_mower_state_with_statistics(
        self, mower_id: Union[str, int]
    ) -> MowerState:
        """Return a mower's state with its statistics attached.

        Fetches the mower state, waits briefly to avoid upstream timeouts, then
        fetches the statistics and stores them on the returned ``MowerState`` as
        ``statistics``. This keeps the pacing concern inside the library so
        consumers can issue a single call.
        """
        mower = await self.receive_mower_by_id(mower_id)
        await asyncio.sleep(self._STATISTICS_FETCH_DELAY_SECONDS)
        mower.__dict__["statistics"] = await self.receive_mower_statistics(
            mower_id
        )
        return mower

    async def receive_mower_week_mow_time_in_hours(
        self, mower_id: Union[str, int]
    ) -> dict:
        logger.debug("receive_mower_week_mow_time_in_hours: %s", mower_id)
        mow_times = await self._request_json(
            f"{IMOW_API_URI}/mowers/{mower_id}/statistics/week-mow-time-in-hours/",
            "GET",
        )
        logger.debug(mow_times)
        return mow_times

    async def receive_mower_start_points(self, mower_id: Union[str, int]) -> list:
        logger.debug("receive_mower_start_points: %s", mower_id)
        start_points = await self._request_json(
            f"{IMOW_API_URI}/mowers/{mower_id}/start-points/", "GET"
        )
        for startpoint in start_points:
            logger.debug("  - %s", startpoint)
        return start_points
