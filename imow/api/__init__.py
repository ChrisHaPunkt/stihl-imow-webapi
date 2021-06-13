from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from typing import Tuple, Union, List
from urllib.parse import quote

import aiohttp
from aiohttp import ClientSession, ClientResponseError
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
from imow.common.package_descriptions import *

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
            await self.http_session.close()
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
                self.http_session = None
                self.csrf_token = None
                self.requestId = None
                self.access_token: str = ""
                self.token_expires: datetime = None
            if not self.api_email and not self.api_password:
                raise LoginError("Got no credentials to authenticate, please provide")
            await self.__authenticate(self.api_email, self.api_password)
            logger.debug("Get Token: Re-Authenticate")

        await self.validate_token()
        if return_expire_time:
            return self.access_token, self.token_expires
        else:
            return self.access_token

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
    ) -> [str, str, aiohttp.ClientResponse]:
        """
        try the authentication request with fetched csrf and requestId payload
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :return: the newly created access token, and expire time besides the legacy response
        """
        await self.__fetch_new_csrf_token_and_request_id()
        url = f"{IMOW_OAUTH_URI}/authentication/authenticate/?lang=de"
        encoded_mail = quote(email)
        payload = f"mail={encoded_mail}&password={password}&csrf-token={self.csrf_token}&requestId={self.requestId}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        response = await self.api_request(url, "POST", payload=payload, headers=headers)

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

    async def __fetch_new_csrf_token_and_request_id(self) -> [str, str]:
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
            upstream_csrf_token = soup.find("input", {"name": "csrf-token"}).get(
                "value"
            )
            upstream_request_id = soup.find("input", {"name": "requestId"}).get("value")
        except AttributeError:
            raise ProcessLookupError(
                "Did not found necessary csrf token and/or request id in html source"
            )

        self.csrf_token = upstream_csrf_token
        self.requestId = upstream_request_id
        logger.debug("CSRF: new token and request id <Redacted>")
        return self.csrf_token, self.requestId

    async def fetch_messages(self):
        try:
            url_en = f"https://app.imow.stihl.com/assets/i18n/animations/en.json"
            response_en = await self.http_session.request("GET", url_en)
            i18n_en = json.loads(await response_en.text())
            self.messages_en = Messages(i18n_en)
            if self.lang != "en":
                url_user = f"https://app.imow.stihl.com/assets/i18n/animations/{self.lang}.json"
                response_user = await self.http_session.request("GET", url_user)
                i18n_user = json.loads(await response_user.text())
                self.messages_user = Messages(i18n_user)
            else:
                self.messages_user = self.messages_en

        except ClientResponseError as e:
            if e.status == 404:
                await self.close()
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

            return await self.http_session.request(
                method, url, headers=headers_obj, data=payload
            )
        except ClientResponseError as e:
            if e.status == 500:
                await self.check_api_maintenance()
            raise e

    async def intent(
        self,
        imow_action: IMowActions,
        mower_name: str = "",
        mower_id: str = "",
        mower_action_id: str = "",
        startpoint: any = "0",
        duration: int = 30,
    ) -> aiohttp.ClientResponse:
        """
        Intent to do a action. This seems to create a job object upstream. The action object contains an action Enum,
        the action Value is <MowerExternalId> or <MowerExternalId,DurationInMunitesDividedBy10,StartPoint> if
        startMowing is chosen

        :param imow_action: Anything from imow.common.actions
        :param mower_name: sth to identify which mower is used
        :param mower_id: sth to identify which mower is used
        :param mower_action_id:
            necessary identifier for the mowers for actions.
            This is looked up, if only mower_name or mower_id is provided

        :param startpoint: point from which the mowing shall start, default to 0
        :param duration: minutes of intended mowing defaults, to 30 minutes
        :return:
        """
        if not mower_action_id and not mower_id and not mower_name:
            raise AttributeError(
                "Need some mower to work on. Please specify mower_[name|id|action_id]"
            )
        if not mower_action_id and mower_name:
            mower_action_id = await self.get_mower_action_id_from_name(mower_name)
        if not mower_action_id and mower_id:
            mower_action_id = await self.get_mower_action_id_from_id(mower_id)

        if len(mower_action_id) < 16:
            raise AttributeError(
                f"Invalid mower_action_id, need exactly 16 chars, got {len(mower_action_id)} in {mower_action_id}"
            )

        url = f"{IMOW_API_URI}/mower-actions/"

        action_value = (
            f"{mower_action_id},{str(int(duration / 10))},{str(startpoint)}"
            if imow_action == IMowActions.START_MOWING
            else mower_action_id
        )

        action_object = {
            "actionName": imow_action.value,
            "actionValue": action_value
            # "0000000123456789,15,0" <MowerExternalId,DurationInMunitesDividedBy10,StartPoint>
        }
        logger.debug(f"Intend: {action_object}")

        payload = json.dumps(action_object)

        response = await self.api_request(url, "POST", payload=payload)
        logger.debug(f"Sent mower {mower_action_id} to {imow_action}")
        return response

    async def get_status_by_name(self, mower_name: str) -> dict:
        logger.debug(f"get_status_by_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.status
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def get_status_by_id(self, mower_id=(str, int)) -> dict:
        if not type(mower_id) == str:
            mower_id = str(mower_id)
        logger.debug(f"get_status_by_id: {mower_id}")
        try:
            response = await self.receive_mower_by_id(mower_id)
            return response.status
        except ConnectionError:
            raise LookupError(f"Mower with id {mower_id} not found in upstream")

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
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def get_mower_action_id_from_id(self, mower_id: str) -> str:
        logger.debug(f"get_mower_action_id_from_id: {mower_id}")
        try:
            response = await self.receive_mower_by_id(mower_id)
            return response.externalId
        except ConnectionError:
            raise LookupError(f"Mower with id {mower_id} not found in upstream")

    async def get_mower_id_from_name(self, mower_name: str) -> str:
        logger.debug(f"get_mower_id_from_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                return mower.id
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def receive_mowers(self) -> List[MowerState]:
        logger.debug(f"receive_mowers:")
        mowers = []
        response = await self.api_request(f"{IMOW_API_URI}/mowers/", "GET")
        for mower in json.loads(await response.text()):
            mowers.append(MowerState(mower, self))
        logger.debug(mowers)
        return mowers

    async def receive_mower_by_name(self, mower_name: str) -> MowerState:
        logger.debug(f"get_mower_from_name: {mower_name}")
        for mower in await self.receive_mowers():
            if mower.name == mower_name:
                logger.debug(mower)
                return mower
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    async def receive_mower_by_id(self, mower_id: str) -> MowerState:
        logger.debug(f"receive_mower: {mower_id}")
        response = await self.api_request(f"{IMOW_API_URI}/mowers/{mower_id}/", "GET")
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

    async def receive_mower_week_mow_time_in_hours(self, mower_id: str) -> dict:
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
        logger.debug(start_points)
        return start_points
