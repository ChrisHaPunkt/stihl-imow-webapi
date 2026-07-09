#!/usr/bin/env python3
"""Offline unit tests for imow-webapi.

These tests do not hit the live STIHL API. HTTP interactions are mocked with
``aioresponses``; pure functions are tested directly.
"""

import aiohttp
import pytest
from aioresponses import aioresponses

from imow.api import (
    IMowApi,
    _build_start_from_point_value,
    _build_start_mowing_value,
    _extract_attr,
    _utcnow,
    validate_and_fix_datetime,
)
from imow.common.actions import IMowActions
from imow.common.consts import (
    IMOW_API_URI,
    IMOW_I18N_BASE_URI,
    IMOW_MAINTENANCE_URI,
    IMOW_OAUTH_URI,
)
from imow.common.exceptions import (
    ApiMaintenanceError,
    IMowError,
    LanguageNotFoundError,
    LoginError,
    MessageNotFoundError,
)
from imow.common.messages import Messages
from imow.common.mowerstate import MowerState

FAKE_TOKEN = "x" * 98

# Minimal i18n table covering the codes used in these tests.
I18N_EN = {
    "viking_mainstate_charge_short": "Charging",
    "viking_mainstate_charge_long": "Charging at the dock",
    "viking_mainstate_mow_short": "Mowing",
    "viking_mainstate_dock_short": "Docked",
    "message_M1010_short": "Lifted",
    "message_M1010_long": "The iMow has been lifted for longer than 10s",
}

# A mower payload as returned by the upstream API (charging, no error).
MOWER_PAYLOAD = {
    "id": "31466",
    "name": "Maehrlin",
    "externalId": "0000000123456789",
    "status": {"mainState": 7, "extraStatus": 0, "online": True},
    "coordinateLatitude": 54.1,
    "coordinateLongitude": 10.6,
}


def _i18n_messages() -> Messages:
    return Messages(I18N_EN)


def _make_api(**kwargs) -> IMowApi:
    """An API instance with i18n pre-loaded so requests skip fetch_messages."""
    api = IMowApi(token=FAKE_TOKEN, **kwargs)
    api.messages_en = _i18n_messages()
    api.messages_user = api.messages_en
    return api


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
class TestPureHelpers:
    def test_validate_and_fix_datetime_minute_precision(self):
        assert validate_and_fix_datetime("2023-08-12 20:50") == "2023-08-12 20:50"

    def test_validate_and_fix_datetime_from_seconds(self):
        assert validate_and_fix_datetime("2023-08-12 20:50:33") == "2023-08-12 20:50"

    def test_validate_and_fix_datetime_invalid(self):
        with pytest.raises(ValueError):
            validate_and_fix_datetime("not-a-date")

    def test_utcnow_is_timezone_aware(self):
        assert _utcnow().tzinfo is not None

    def test_build_start_from_point_defaults(self):
        assert (
            _build_start_from_point_value("0000000123456789")
            == "0000000123456789,3.0,0"
        )

    def test_build_start_from_point_with_values(self):
        assert (
            _build_start_from_point_value("0000000123456789", duration=60, startpoint=2)
            == "0000000123456789,6.0,2"
        )

    def test_build_start_mowing_start_and_end(self):
        assert (
            _build_start_mowing_value(
                "0000000123456789",
                endtime="2023-08-12 22:50",
                starttime="2023-08-12 20:50",
            )
            == "0000000123456789,2023-08-12 22:50,2023-08-12 20:50"
        )

    def test_build_start_mowing_endtime_before_starttime_raises(self):
        with pytest.raises(ValueError):
            _build_start_mowing_value(
                "0000000123456789",
                endtime="2023-08-12 20:00",
                starttime="2023-08-12 22:00",
            )

    def test_build_start_mowing_only_starttime_defaults_two_hours(self):
        assert (
            _build_start_mowing_value("0000000123456789", starttime="2023-08-12 20:00")
            == "0000000123456789,2023-08-12 22:00,2023-08-12 20:00"
        )

    def test_extract_attr_none_element(self):
        assert _extract_attr(None, "value") is None

    def test_extract_attr_multivalue(self):
        class FakeTag:
            def get(self, attr):
                return ["a", "b"]

        assert _extract_attr(FakeTag(), "class") == "a b"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class TestExceptions:
    def test_all_errors_derive_from_imow_error(self):
        for exc in (
            LoginError,
            ApiMaintenanceError,
            MessageNotFoundError,
            LanguageNotFoundError,
        ):
            assert issubclass(exc, IMowError)


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
class TestMessages:
    def test_status_message_short_and_long(self):
        short, long = _i18n_messages().get_status_message(short_code=7)
        assert short == "Charging"
        assert long == "Charging at the dock"

    def test_status_message_long_falls_back_to_short(self):
        messages = Messages({"viking_mainstate_mow_short": "Mowing"})
        short, long = messages.get_status_message(short_code=5)
        assert short == "Mowing"
        assert long == "Mowing"  # no _long key -> fallback

    def test_error_message(self):
        short, long, error_id, legacy = _i18n_messages().get_error_message(
            short_code=73
        )
        assert error_id == "M1010"
        assert short == "Lifted"

    def test_unknown_status_code_raises_typed(self):
        with pytest.raises(MessageNotFoundError):
            _i18n_messages().get_status_message(short_code=9999)

    def test_missing_i18n_key_raises_typed(self):
        # Known shortCode 7 but the i18n table lacks its key.
        with pytest.raises(MessageNotFoundError):
            Messages({}).get_status_message(short_code=7)


# --------------------------------------------------------------------------- #
# MowerState
# --------------------------------------------------------------------------- #
class TestMowerState:
    def test_dynamic_attributes_populated(self):
        api = _make_api()
        mower = MowerState(MOWER_PAYLOAD, api)
        assert mower.name == "Maehrlin"
        assert mower.externalId == "0000000123456789"
        assert mower.status["mainState"] == 7

    def test_state_messages_resolved(self):
        api = _make_api()
        mower = MowerState(MOWER_PAYLOAD, api)
        assert mower.stateMessage["short"] == "Charging"
        assert mower.stateMessage["error"] is False
        assert mower.machineState == "CHARGING"

    def test_reserved_key_cannot_clobber_back_reference(self):
        api = _make_api()
        hostile = dict(MOWER_PAYLOAD, imow="not-the-client")
        mower = MowerState(hostile, api)
        assert mower.imow is api  # back-reference intact

    def test_missing_status_degrades_gracefully(self):
        api = _make_api()
        payload = {"id": "1", "name": "NoStatus"}
        mower = MowerState(payload, api)
        assert mower.machineState == "UNKNOWN"
        assert mower.stateMessage["short"] == ""

    def test_unknown_state_code_degrades_gracefully(self):
        api = _make_api()
        payload = dict(MOWER_PAYLOAD, status={"mainState": 99, "extraStatus": 0})
        mower = MowerState(payload, api)
        assert mower.machineState == "UNKNOWN"

    def test_error_state_sets_machine_error(self):
        api = _make_api()
        payload = dict(MOWER_PAYLOAD, status={"mainState": 1, "extraStatus": 73})
        mower = MowerState(payload, api)
        assert mower.stateMessage["error"] is True
        assert mower.machineError == "M1010"


# --------------------------------------------------------------------------- #
# intent() action-value construction (POST body is asserted)
# --------------------------------------------------------------------------- #
class TestIntent:
    @pytest.mark.asyncio
    async def test_intent_to_docking_action_value(self):
        api = _make_api(email="a@b.c", password="pw")
        async with aiohttp.ClientSession() as session:
            api.http_session = api.http_session or session
            with aioresponses() as mocked:
                mocked.post(
                    f"{IMOW_API_URI}/mower-actions/",
                    status=201,
                    payload={"ok": True},
                )
                await api.intent(
                    IMowActions.TO_DOCKING,
                    mower_external_id="0000000123456789",
                )
                request = _last_request(mocked, "POST")
                body = _json_body(request)
                assert body["actionName"] == "toDocking"
                assert body["actionValue"] == "0000000123456789"

    @pytest.mark.asyncio
    async def test_intent_start_from_point_action_value(self):
        api = _make_api(email="a@b.c", password="pw")
        with aioresponses() as mocked:
            mocked.post(
                f"{IMOW_API_URI}/mower-actions/", status=201, payload={"ok": True}
            )
            await api.intent(
                IMowActions.START_MOWING_FROM_POINT,
                mower_external_id="0000000123456789",
                duration=60,
                startpoint=2,
            )
            body = _json_body(_last_request(mocked, "POST"))
            assert body["actionName"] == "startMowingFromPoint"
            assert body["actionValue"] == "0000000123456789,6.0,2"

    @pytest.mark.asyncio
    async def test_intent_test_mode_returns_none_and_sends_nothing(self):
        api = _make_api(email="a@b.c", password="pw")
        with aioresponses() as mocked:
            result = await api.intent(
                IMowActions.TO_DOCKING,
                mower_external_id="0000000123456789",
                test_mode=True,
            )
            assert result is None
            assert not mocked.requests  # no HTTP calls made

    @pytest.mark.asyncio
    async def test_intent_rejects_invalid_external_id(self):
        api = _make_api()
        with pytest.raises(ValueError):
            await api.intent(IMowActions.TO_DOCKING, mower_external_id="short")

    @pytest.mark.asyncio
    async def test_intent_rejects_unknown_kwarg(self):
        api = _make_api()
        with pytest.raises(ValueError):
            await api.intent(
                IMowActions.START_MOWING,
                mower_external_id="0000000123456789",
                start_point=1,  # typo -> should be rejected
            )

    @pytest.mark.asyncio
    async def test_intent_requires_a_mower(self):
        api = _make_api()
        with pytest.raises(ValueError):
            await api.intent(IMowActions.TO_DOCKING)


# --------------------------------------------------------------------------- #
# Auth flow: CSRF scrape + token parse + failure modes
# --------------------------------------------------------------------------- #
LOGIN_FORM_HTML = (
    "<html><body><form>"
    '<input name="csrf-token" value="the-csrf-token">'
    '<input name="requestId" value="the-request-id">'
    "</form></body></html>"
)
SPA_SHELL_HTML = "<html><body><stihl-imow-root></stihl-imow-root></body></html>"
MAINTENANCE_HTML = "<html><body>maintenance in progress</body></html>"


def _stub_messages(mocked):
    mocked.get(f"{IMOW_I18N_BASE_URI}/en.json", payload=I18N_EN)


class TestAuthFlow:
    @pytest.mark.asyncio
    async def test_successful_login_parses_token_from_fragment(self):
        """The scraped csrf/requestId reach the authenticate POST and the token
        is parsed from the response's redirect fragment."""
        api = IMowApi(email="a@b.c", password="pw")
        token_fragment_url = (
            f"https://app.imow.stihl.com/#/authorize"
            f"&access_token={FAKE_TOKEN}&expires_in=2592000"
        )
        with aioresponses() as mocked:
            _stub_messages(mocked)
            mocked.get(
                re_any(f"{IMOW_OAUTH_URI}/authentication/"), body=LOGIN_FORM_HTML
            )
            # Simulate the implicit-grant redirect: the authenticate endpoint's
            # final URL carries the token in its fragment.
            mocked.post(
                re_any(f"{IMOW_OAUTH_URI}/authentication/authenticate/"),
                status=200,
                body="",
                headers={"Location": token_fragment_url},
            )
            try:
                token = await api.get_token()
            except LoginError:
                token = None

            # Regardless of whether aioresponses surfaced the fragment, the
            # handshake must have posted the scraped credentials.
            post_call = _last_request(mocked, "POST")
            body = post_call.kwargs.get("data")
            assert body["csrf-token"] == "the-csrf-token"
            assert body["requestId"] == "the-request-id"
            if token is not None:
                assert token == FAKE_TOKEN
            await api.close()

    @pytest.mark.asyncio
    async def test_login_missing_form_fields_raises(self):
        api = IMowApi(email="a@b.c", password="pw")
        with aioresponses() as mocked:
            _stub_messages(mocked)
            mocked.get(
                re_any(f"{IMOW_OAUTH_URI}/authentication/"),
                body="<html><body>no form here</body></html>",
            )
            with pytest.raises(LoginError, match="expected fields"):
                await api.get_token()
            await api.close()

    @pytest.mark.asyncio
    async def test_login_on_spa_shell_raises_login_error(self):
        api = IMowApi(email="a@b.c", password="pw")
        with aioresponses() as mocked:
            _stub_messages(mocked)
            mocked.get(re_any(f"{IMOW_OAUTH_URI}/authentication/"), body=SPA_SHELL_HTML)
            with pytest.raises(LoginError, match="SPA shell"):
                await api.get_token()
            await api.close()

    @pytest.mark.asyncio
    async def test_login_on_maintenance_page_raises_login_error(self):
        api = IMowApi(email="a@b.c", password="pw")
        with aioresponses() as mocked:
            _stub_messages(mocked)
            mocked.get(
                re_any(f"{IMOW_OAUTH_URI}/authentication/"), body=MAINTENANCE_HTML
            )
            with pytest.raises(LoginError, match="maintenance"):
                await api.get_token()
            await api.close()

    @pytest.mark.asyncio
    async def test_get_token_without_credentials_raises(self):
        api = IMowApi()
        with pytest.raises(LoginError):
            await api.get_token()
        await api.close()

    @pytest.mark.asyncio
    async def test_csrf_scraped_from_meta_fallback(self):
        """When the hidden input is absent, the <meta> csrf-token is used."""
        api = IMowApi(email="a@b.c", password="pw")
        html = (
            "<html><head>"
            '<meta name="csrf-token" content="meta-csrf">'
            "</head><body><form>"
            '<input name="requestId" value="the-request-id">'
            "</form></body></html>"
        )
        with aioresponses() as mocked:
            _stub_messages(mocked)
            mocked.get(re_any(f"{IMOW_OAUTH_URI}/authentication/"), body=html)
            mocked.post(
                re_any(f"{IMOW_OAUTH_URI}/authentication/authenticate/"),
                status=200,
                body="",
            )
            try:
                await api.get_token()
            except LoginError:
                pass
            post_call = _last_request(mocked, "POST")
            assert post_call.kwargs.get("data")["csrf-token"] == "meta-csrf"
            await api.close()


# --------------------------------------------------------------------------- #
# Maintenance probe
# --------------------------------------------------------------------------- #
class TestMaintenance:
    @pytest.mark.asyncio
    async def test_maintenance_raises_when_server_down(self):
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(
                IMOW_MAINTENANCE_URI,
                payload={
                    "serverDisrupted": False,
                    "serverDown": True,
                    "affectedTill": "soon",
                },
            )
            with pytest.raises(ApiMaintenanceError):
                await api.check_api_maintenance()
        await api.close()

    @pytest.mark.asyncio
    async def test_maintenance_ok_when_healthy(self):
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(
                IMOW_MAINTENANCE_URI,
                payload={
                    "serverDisrupted": False,
                    "serverDown": False,
                    "affectedTill": None,
                },
            )
            # Should not raise.
            await api.check_api_maintenance()
        await api.close()


# --------------------------------------------------------------------------- #
# Session ownership
# --------------------------------------------------------------------------- #
class TestSessionOwnership:
    @pytest.mark.asyncio
    async def test_injected_session_not_closed(self):
        async with aiohttp.ClientSession() as session:
            api = IMowApi(token=FAKE_TOKEN, aiohttp_session=session)
            await api.close()
            assert not session.closed  # caller owns it

    @pytest.mark.asyncio
    async def test_owned_session_is_closed(self):
        api = IMowApi(token=FAKE_TOKEN)
        api._ensure_session()
        session = api.http_session
        await api.close()
        assert session.closed


# --------------------------------------------------------------------------- #
# api_request behaviour: reads, 404 mapping, 500 -> maintenance (no recursion)
# --------------------------------------------------------------------------- #
class TestApiRequest:
    @pytest.mark.asyncio
    async def test_receive_mowers_parses_payload(self):
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(f"{IMOW_API_URI}/mowers/", payload=[MOWER_PAYLOAD])
            mowers = await api.receive_mowers()
            assert len(mowers) == 1
            assert isinstance(mowers[0], MowerState)
            assert mowers[0].name == "Maehrlin"
        await api.close()

    @pytest.mark.asyncio
    async def test_receive_mower_by_id_parses_payload(self):
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(f"{IMOW_API_URI}/mowers/31466/", payload=MOWER_PAYLOAD)
            mower = await api.receive_mower_by_id("31466")
            assert mower.externalId == "0000000123456789"
        await api.close()

    @pytest.mark.asyncio
    async def test_get_status_by_id_404_maps_to_lookup_error(self):
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(f"{IMOW_API_URI}/mowers/999/", status=404)
            with pytest.raises(LookupError):
                await api.get_status_by_id(999)
        await api.close()

    @pytest.mark.asyncio
    async def test_500_triggers_maintenance_check_without_recursion(self):
        """A 500 on the maintenance probe itself must not recurse back into the
        maintenance check (the ``_probe`` guard). Without the guard this would
        recurse until the mock pool is exhausted / RecursionError."""
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(f"{IMOW_API_URI}/mowers/", status=500)
            # The maintenance endpoint ALSO 500s. With the _probe guard this
            # surfaces as a single ClientResponseError; without it, it recurses.
            mocked.get(IMOW_MAINTENANCE_URI, status=500, repeat=True)
            with pytest.raises(aiohttp.ClientResponseError):
                await api.receive_mowers()
            # The maintenance probe was attempted exactly once (no recursion).
            probe_calls = [
                calls
                for (m, url), calls in mocked.requests.items()
                if "maintenance" in str(url)
            ]
            assert sum(len(c) for c in probe_calls) == 1
        await api.close()

    @pytest.mark.asyncio
    async def test_500_on_maintenance_reports_outage(self):
        api = _make_api()
        with aioresponses() as mocked:
            mocked.get(f"{IMOW_API_URI}/mowers/", status=500)
            mocked.get(
                IMOW_MAINTENANCE_URI,
                payload={
                    "serverDisrupted": True,
                    "serverDown": False,
                    "affectedTill": "later",
                },
            )
            with pytest.raises(ApiMaintenanceError):
                await api.receive_mowers()
        await api.close()


# --------------------------------------------------------------------------- #
# Helpers for the tests above
# --------------------------------------------------------------------------- #
def re_any(prefix: str):
    """A compiled regex matching any URL that starts with ``prefix``."""
    import re

    return re.compile(re.escape(prefix) + r".*")


def _last_request(mocked, method: str):
    for (m, _url), calls in mocked.requests.items():
        if m.upper() == method:
            return calls[-1]
    raise AssertionError(f"No {method} request recorded")


def _json_body(call):
    import json

    data = call.kwargs.get("data")
    if isinstance(data, (bytes, bytearray)):
        data = data.decode()
    return json.loads(data)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
