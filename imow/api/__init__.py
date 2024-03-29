from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import Tuple, Union, List, Any
from urllib.parse import quote

import aiohttp
from aiohttp import ClientSession, ClientResponseError, ClientResponse
from bs4 import BeautifulSoup
from furl import furl

from imow.common.actions import IMowActions
from imow.common.consts import IMOW_OAUTH_URI, IMOW_API_URI
from imow.common.exceptions import (
    LoginError,
    ApiMaintenanceError,
    LanguageNotFoundError,
)
from imow.common.messages import Messages
from imow.common.mowerstate import MowerState
from imow.common.package_descriptions import (
    python_major,
    python_minor,
    package_name,
)

logger = logging.getLogger("imow")

try:
    assert sys.version_info >= (int(python_major), int(python_minor))
except AssertionError:
    raise RuntimeError(
        f"{package_name!r} requires Python {python_major}.{python_minor}+ (You have Python {sys.version})"
    )
if (
    sys.version_info[0] == 3
    and sys.version_info[1] >= 8
    and sys.platform.startswith("win")
):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def validate_and_fix_datetime(value) -> str:
    """
    Try to convert and validate the given string from "%Y-%m-%d %H:%M" or "%Y-%m-%d %H:%M:%S into a datetime object
    and give the needed "%Y-%m-%d %H:%M" string back.
    :param value: the string tobe checked :return: the correctly formated string
    """
    try:
        datetime_object = datetime.strptime(value, "%Y-%m-%d %H:%M")
        return datetime_object.strftime("%Y-%m-%d %H:%M")
    except ValueError as ve:
        logger.warning(
            f"  Try fixing given time format because {ve} in {value}"
        )
        try:
            datetime_object = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return datetime_object.strftime("%Y-%m-%d %H:%M")
        except ValueError as ve2:
            raise ValueError(f'Unsupported "time" argument: {value} -> {ve2}')


class IMowApi:
    def __init__(
        self,
        email: str = None,
        password: str = None,
        token: str = None,
        aiohttp_session: ClientSession = None,
        lang: str = "en",
    ) -> None:
        self.http_session: ClientSession = aiohttp_session
        self.csrf_token: str = ""
        self.requestId: str = ""
        self.access_token: str = token
        self.token_expires: datetime = None
        self.api_email: str = email
        self.api_password: str = password
        self.lang = lang
        self.messages_user = None
        self.messages_en = None

    async def close(self):
        """Cleanup the aiohttp Session"""
        await asyncio.sleep(0.250)
        await self.http_session.close()

    async def check_api_maintenance(self) -> None:
        url = "https://app-api-maintenance-r-euwe-4bf2d8.azurewebsites.net/maintenance/"

        headers = {
            "Authorization": "",
        }
        response = await self.api_request(url, "GET", headers=headers)
        status = json.loads(await response.text())
        logger.debug(status)
        if status["serverDisrupted"] or status["serverDown"]:
            msg = (
                f"iMow API is under Maintenance -> "
                f'serverDisrupted: {status["serverDisrupted"]}, serverDown: {status["serverDown"]}, '
                f'affectedTill {status["affectedTill"]}'
            )
            raise ApiMaintenanceError(msg)

    async def get_token(
        self,
        email: str = "",
        password: str = "",
        force_reauth=False,
        return_expire_time=False,
    ) -> Union[Tuple[str, datetime], str]:
        """
        look for a token, if present, return. Else authenticate and store new token
        :param return_expire_time:
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :param force_reauth: Force a re-authentication with username and password
        :return: tuple, the access token and a datetime object containing the expire date
        """

        if not self.access_token or force_reauth:
            if email and password:
                self.api_password = password
                self.api_email = email
            if force_reauth:
                await self.api_logout()
                self.csrf_token = ""
                self.requestId = ""
                self.access_token: str = ""
                self.token_expires: datetime = None
            if not self.api_email and not self.api_password:
                raise LoginError(
                    "Got no credentials to authenticate, please provide"
                )
            await self.__authenticate(self.api_email, self.api_password)
            logger.debug("Get Token: Re-Authenticate")

        await self.validate_token()
        if return_expire_time:
            return self.access_token, self.token_expires
        else:
            return self.access_token

    async def api_logout(self):
        if not self.http_session or self.http_session.closed:
            self.http_session = aiohttp.ClientSession(raise_for_status=True)
        async with self.http_session.post(
            "https://oauth2.imow.stihl.com/authentication/logout/",
            data={
                "csrf-token": self.csrf_token,
                "logoutUrl": "https://app.imow.stihl.com",
                "clientId": "9526273B-1477-47C6-801C-4356F58EF883",
                "cancelUrl": "https://app.imow.stihl.com",
            },
        ) as resp:
            await resp.read()
        self.http_session.cookie_jar.clear_domain("https://app.imow.stihl.com")
        self.http_session.cookie_jar.clear_domain(
            "https://oauth2.imow.stihl.com/"
        )

    async def validate_token(self, explicit_token: str = None) -> bool:
        old_token = None
        if explicit_token:
            # save old instance token and place temp token for validation
            old_token = self.access_token
            self.access_token = explicit_token

        await self.receive_mowers()

        if explicit_token:
            # Reset instance token
            self.access_token = old_token
        return True

    async def __authenticate(
        self, email: str, password: str
    ) -> tuple[Any, datetime, ClientResponse]:
        """
        try the authentication request with fetched csrf and requestId payload
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :return: the newly created access token, and expire time besides the legacy response
        """

        await self.__fetch_new_csrf_token_and_request_id()
        url = f"{IMOW_OAUTH_URI}/authentication/authenticate/?lang={self.lang}"
        encoded_mail = quote(email)
        encoded_password = quote(password)
        payload = (
            f"mail={encoded_mail}&password={encoded_password}"
            f"&csrf-token={self.csrf_token}&requestId={self.requestId} "
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        response = await self.api_request(
            url, "POST", payload=payload, headers=headers
        )

        response_url_query_args = furl(response.real_url).fragment.args
        if "access_token" not in response_url_query_args:
            raise LoginError(
                "STIHL iMow did not return an access_token, check your credentials"
            )

        self.access_token = response_url_query_args["access_token"]
        self.token_expires = datetime.now() + timedelta(
            seconds=int(response_url_query_args["expires_in"])
        )
        return self.access_token, self.token_expires, response

    async def __fetch_new_csrf_token_and_request_id(
        self,
    ) -> tuple[str | list[str] | None, str | list[str] | None]:
        """
        Fetch a new csrf_token and requestId to do the authentication as expected by the api
        csrf_token and requestId are used as payload within authentication
        """

        # URL needs whole redirect query parameter
        url = (
            f"{IMOW_OAUTH_URI}/authentication/?lang=de_DE&authorizationRedirectUrl=https%3A%2F%2Foauth2"
            ".imow.stihl.com%2Fauthorization%2F%3Fresponse_type%3Dtoken%26client_id%3D9526273B-1477-47C6-801C"
            "-4356F58EF883%26redirect_uri%3Dhttps%253A%252F%252Fapp.imow.stihl.com%252F%2523%252Fauthorize%26state"
        )
        response = await self.api_request(url, "GET")

        soup = BeautifulSoup(await response.text(), "html.parser")
        try:
            upstream_csrf_token = soup.find(
                "input", {"name": "csrf-token"}
            ).get("value")
            upstream_request_id = soup.find(
                "input", {"name": "requestId"}
            ).get("value")
        except AttributeError:
            raise ProcessLookupError(
                "Did not find necessary csrf token and/or request id in html source"
            )

        self.csrf_token = upstream_csrf_token
        self.requestId = upstream_request_id
        logger.debug("CSRF: new token and request id <redacted>")
        return self.csrf_token, self.requestId

    async def fetch_messages(self):
        try:
            url_en = (
                "https://app.imow.stihl.com/assets/i18n/animations/en.json"
            )
            async with self.http_session.request("GET", url_en) as response_en:
                i18n_en = json.loads(await response_en.text())
            self.messages_en = Messages(i18n_en)
            if self.lang != "en":
                url_user = f"https://app.imow.stihl.com/assets/i18n/animations/{self.lang}.json"
                async with self.http_session.request(
                    "GET", url_user
                ) as response_user:
                    i18n_user = json.loads(await response_user.text())
                    self.messages_user = Messages(i18n_user)
            else:
                self.messages_user = self.messages_en

        except ClientResponseError as e:
            if e.status == 404:
                raise LanguageNotFoundError(
                    f"Language-File '{self.lang}.json' not found on imow upstream ("
                    f"https://app.imow.stihl.com/assets/i18n/animations/{self.lang}.json)"
                )

    async def api_request(
        self, url, method, payload=None, headers=None
    ) -> aiohttp.ClientResponse:
        """
        Do a standardized request against the stihl imow webapi, with predefined headers
        :param url: The target URL
        :param method: The Method to use
        :param payload: optional payload
        :param headers: optional update headers
        :return: the aiohttp.ClientResponse
        """
        if not self.http_session or self.http_session.closed:
            self.http_session = aiohttp.ClientSession(raise_for_status=True)
        if not self.messages_en:
            await self.fetch_messages()
        if (
            self.token_expires
            and (self.token_expires - datetime.now()).days <= 1
        ):
            logger.info(
                "Fetching new access_token because old one expires in less than 1 day"
            )
            await self.get_token(force_reauth=True)

        if not payload:
            payload = {}

        headers_obj = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
            "Authorization": f'Bearer {self.access_token if self.access_token else ""}',
            "Origin": "https://app.imow.stihl.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://app.imow.stihl.com/",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "Trailers",
            "Content-Type": "application/json",
        }
        if headers:
            headers_obj.update(headers)
        try:
            async with self.http_session.request(
                method, url, headers=headers_obj, data=payload
            ) as response:
                await response.read()
                response.raise_for_status()
                return response
        except ClientResponseError as e:
            if e.status == 500:
                await self.check_api_maintenance()
            raise e

    async def intent(
        self,
        imow_action: IMowActions,
        mower_name: str = "",
        mower_id: str = "",
        mower_external_id: str = "",
        first_action_value_param: any = "",
        second_action_value_param: any = "",
        test_mode: bool = False,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """
        Intent to do a action. This seems to create a job object upstream. The action object contains an action Enum,
        the action Value is <MowerExternalId> or <MowerExternalId,DurationInMunitesDividedBy10,StartPoint> if
        startMowing is chosen

        :param imow_action: Anything from imow.common.actions
        :param mower_name: sth to identify which mower is used
        :param mower_id: sth to identify which mower is used
        :param mower_external_id:
            necessary identifier for the mowers for actions.
            This is looked up, if only mower_name or mower_id is provided

        :param first_action_value_param: first argument passed into the action call request to the api. Can be one of the following contents:
            A duration: minutes of intented mowing. Used by START_MOWING_FROM_POINT. Defaults to '30' minutes.
            A starttime: a datetime when to start mowing. I.e. '2023-08-12 20:50' used by START_MOWING

        :param second_action_value_param: second argument passed into the action call request to the api. Can be one of the following contents:
            A startpoint: from which the mowing shall start. Used by START_MOWING_FROM_POINT. Defaults to '0'.
            An endtime: a datetime when to stop mowing. I.e. '2023-08-12 20:50' used by START_MOWING
        :param test_mode: Do not issue the request to the server
        :return:
        """
        if test_mode:
            logger.warning("TEST_MODE: Request will not be issued to server.")
        if not mower_external_id and not mower_id and not mower_name:
            raise AttributeError(
                "Need some mower to work on. Please specify mower_[name|id|action_id]"
            )
        if not mower_external_id and mower_name:
            mower_external_id = await self.get_mower_action_id_from_name(
                mower_name
            )
        if not mower_external_id and mower_id:
            mower_external_id = await self.get_mower_action_id_from_id(
                mower_id
            )

        if len(mower_external_id) < 16:
            raise AttributeError(
                f"Invalid mower_action_id, need exactly 16 chars, got {len(mower_external_id)} in {mower_external_id}"
            )

        url = f"{IMOW_API_URI}/mower-actions/"

        given_kwargs = kwargs.items()
        if len(given_kwargs) > 0:
            logger.debug(
                "Translating given intent **kwargs to action_value_param"
            )
            for key, value in given_kwargs:
                logger.debug("  {0} = {1}".format(key, value))
                if key == "duration" and value:
                    first_action_value_param = value
                if key == "startpoint" and value:
                    second_action_value_param = value

                if key == "endtime" and value:
                    first_action_value_param = validate_and_fix_datetime(value)

                if key == "starttime" and value:
                    second_action_value_param = validate_and_fix_datetime(
                        value
                    )

            logger.debug(
                f"  -> first_action_value_param (end-time / duration): {first_action_value_param} "
            )
            logger.debug(
                f"  -> second_action_value_param (start-time / startpoint): {second_action_value_param} "
            )

        logger.debug(
            f'Build action object for: {imow_action} -> "{imow_action.value}"'
        )
        # Build other action values depending on given ACTION
        if (
            imow_action == IMowActions.START_MOWING_FROM_POINT
        ):  # Add the duration and startpoint parameter
            duration = (
                str(int(first_action_value_param) / 10)
                if first_action_value_param
                else 30 / 10
            )
            startpoint = (
                str(second_action_value_param)
                if second_action_value_param
                else "0"
            )

            action_value = f"{mower_external_id},{duration},{startpoint}"

        elif (
            imow_action == IMowActions.START_MOWING
        ):  # by start- and/or endtime
            endtime = (
                str(first_action_value_param)
                if first_action_value_param != ""
                else None
            )
            starttime = (
                str(second_action_value_param)
                if second_action_value_param != ""
                else None
            )

            # Create some defaults
            if starttime and not endtime:
                # Run for 2 hours from start time if only a start time is given
                endtime = (
                    datetime.strptime(starttime, "%Y-%m-%d %H:%M")
                    + timedelta(hours=2)
                ).strftime("%Y-%m-%d %H:%M")
            elif not starttime and not endtime:
                # Run for 2 hours from now if no time is given
                now = datetime.now()
                logger.warning(
                    f"No start- or endtime is given. Creating an action object with endtime 2 hours from now"
                    f"based from this machines local timezone. datetime.now() gives {now.strftime('%Y-%m-%d %H:%M')}."
                )
                endtime = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")

            if starttime:
                # Make sure endtime is after starttime
                if datetime.strptime(
                    starttime, "%Y-%m-%d %H:%M"
                ) < datetime.strptime(endtime, "%Y-%m-%d %H:%M"):
                    action_value = f"{mower_external_id},{endtime},{starttime}"
                else:
                    raise AttributeError(
                        f"Time when to end: {endtime} is not afer time to start: {starttime}. This has to be until time travel."
                    )
            else:
                action_value = f"{mower_external_id},{endtime}"

        else:
            action_value = mower_external_id

        action_object = {
            "actionName": imow_action.value,
            "actionValue": action_value
            # "0000000123456789,15,0" <MowerExternalId,DurationInMunitesDividedBy10,StartPoint>
            # "0000000123456789,15,0" <MowerExternalId,EndTime,StartTime>
        }
        logger.debug(
            f"Intent sent as request body to imow api for mower with identifier: '{mower_name}/{mower_id}/{mower_external_id}'"
        )
        logger.info(f"  {action_object}")

        payload = json.dumps(action_object)

        if not test_mode:
            response = await self.api_request(url, "POST", payload=payload)

            if response.ok:
                logger.debug(
                    f"Success: Created mower (extId:{mower_external_id}) ActionObject with contents:"
                )
                logger.debug(f" {action_object}")
                logger.debug(f" -> (HTTP Status {response.status})")
            else:
                logger.error(f"No success with mower-action: {payload}")
            return response
        else:
            logger.warning(
                f"TEST_MODE: (NOT) Created mower (extId:{mower_external_id}) ActionObject with contents:"
            )
            logger.warning(f"  {action_object}")
            return True

    async def update_setting(self, mower_id, setting, new_value) -> MowerState:
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
        if payload_fields[setting] != new_value:
            payload_fields[setting] = new_value
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "de,en-US;q=0.7,en;q=0.3",
                "Content-Type": "application/json",
                "Origin": "https://app.imow.stihl.com",
                "Connection": "keep-alive",
                "Referer": "https://app.imow.stihl.com/",
                "TE": "Trailers",
            }
            response = await self.api_request(
                url=f"{IMOW_API_URI}/mowers/{mower_state.id}/",
                method="PUT",
                payload=json.dumps(payload_fields, indent=2).encode("utf-8"),
                headers=headers,
            )
            mower_state.replace_state(json.loads(await response.text()))
            return mower_state

        else:
            logger.info(f"{setting} is already {new_value}.")
            return await self.receive_mower_by_id(mower_id)

    async def get_status_by_name(self, mower_name: str) -> dict:
        logger.debug(f"get_status_by_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.status
        raise LookupError(
            f"Mower with name {mower_name} not found in upstream"
        )

    async def get_status_by_id(self, mower_id=(str, int)) -> dict:
        if not type(mower_id) == str:
            mower_id = str(mower_id)
        logger.debug(f"get_status_by_id: {mower_id}")
        try:
            response = await self.receive_mower_by_id(mower_id)
            return response.status
        except ConnectionError:
            raise LookupError(
                f"Mower with id {mower_id} not found in upstream"
            )

    async def get_status_by_action_id(self, mower_action_id: str) -> dict:
        logger.debug(f"get_status_by_action_id: {mower_action_id}")
        for mower in await self.receive_mowers():
            if mower.externalId == mower_action_id:
                return mower.status
        raise LookupError(
            f"Mower with externalId {mower_action_id} not found in upstream"
        )

    async def get_mower_action_id_from_name(self, mower_name: str) -> str:
        logger.debug(f"get_mower_action_id_from_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.externalId
        raise LookupError(
            f"Mower with name {mower_name} not found in upstream"
        )

    async def get_mower_action_id_from_id(self, mower_id: str) -> str:
        logger.debug(f"get_mower_action_id_from_id: {mower_id}")
        try:
            response = await self.receive_mower_by_id(mower_id)
            logger.debug(f" - {response.externalId}")
            return response.externalId
        except ConnectionError:
            raise LookupError(
                f"Mower with id {mower_id} not found in upstream"
            )

    async def get_mower_id_from_name(self, mower_name: str) -> str:
        logger.debug(f"get_mower_id_from_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.id
        raise LookupError(
            f"Mower with name {mower_name} not found in upstream"
        )

    async def receive_mowers(self) -> List[MowerState]:
        logger.debug("receive_mowers: ")
        mowers = []
        response = await self.api_request(f"{IMOW_API_URI}/mowers/", "GET")
        for mower in json.loads(await response.text()):
            mowers.append(MowerState(mower, self))
        for mower in mowers:
            logger.debug(f"  - {mower.name}")
        return mowers

    async def receive_mower_by_name(self, mower_name: str) -> MowerState:
        logger.debug(f"get_mower_from_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                logger.debug(mower)
                return mower
        raise LookupError(
            f"Mower with name {mower_name} not found in upstream"
        )

    async def receive_mower_by_id(self, mower_id: str) -> MowerState:
        logger.debug(f"receive_mower: {mower_id}")
        response = await self.api_request(
            f"{IMOW_API_URI}/mowers/{mower_id}/", "GET"
        )
        mower = MowerState(json.loads(await response.text()), self)
        logger.debug(mower)
        return mower

    async def receive_mower_statistics(self, mower_id: str) -> dict:
        logger.debug(f"receive_mower_statistics: {mower_id}")
        response = await self.api_request(
            f"{IMOW_API_URI}/mowers/{mower_id}/statistic/", "GET"
        )
        stats = json.loads(await response.text())
        logger.debug(stats)
        return stats

    async def receive_mower_week_mow_time_in_hours(
        self, mower_id: str
    ) -> dict:
        logger.debug(f"receive_mower_week_mow_time_in_hours: {mower_id}")
        response = await self.api_request(
            f"{IMOW_API_URI}/mowers/{mower_id}/statistics/week-mow-time-in-hours/",
            "GET",
        )
        mow_times = json.loads(await response.text())
        logger.debug(mow_times)
        return mow_times

    async def receive_mower_start_points(self, mower_id: str) -> dict:
        logger.debug(f"receive_mower_start_points: {mower_id}")
        response = await self.api_request(
            f"{IMOW_API_URI}/mowers/{mower_id}/start-points/", "GET"
        )
        start_points = json.loads(await response.text())
        for startpoint in start_points:
            logger.debug(f"  - {startpoint}")
        return start_points
