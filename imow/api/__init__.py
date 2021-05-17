from __future__ import annotations

import http
import json
import logging
import sys
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from furl import furl

from imow.common.actions import IMowActions
from imow.common.consts import IMOW_OAUTH_URI, IMOW_API_URI
from imow.common.exceptions import LoginError
from imow.common.mowerstate import MowerState
from imow.common.mowertask import MowerTask
from imow.common.package_descriptions import *

logger = logging.getLogger('imow')

try:
    assert sys.version_info >= (int(python_major), int(python_minor))
except AssertionError:
    raise RuntimeError(
        f"{package_name!r} requires Python {python_major}.{python_minor}+ (You have Python {sys.version})")


class IMowApi:

    def __init__(self, email: str = None, password: str = None, token: str = None) -> None:

        if (email is None or password is None) and token is None:
            raise LookupError("No email, password or token provided")

        self.http_session = None
        self.csrf_token = None
        self.requestId = None
        self.access_token = None
        self.token_expires = None
        if token:
            logger.debug("New instance: Use Token")
            self.access_token = token
        if not self.access_token:
            logger.debug("New instance: Authenticate with email and password")
            self.get_token(email, password)

    def get_token(self, email: str = "", password: str = "", force_reauth=False) -> (str, datetime):
        """
        look for a token, if present, return. Else authenticate and store new token
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :param force_reauth: Force a re-authentication with username and password
        :return: tuple, the access token and a datetime object containing the expire date
        """

        if not self.access_token or force_reauth:
            if force_reauth:
                self.http_session = None
                self.csrf_token = None
                self.requestId = None
                self.access_token = None
                self.token_expires = None

            self.__authenticate(email, password)
            logger.debug("Get Token: Re-Authenticate")

        return self.access_token, self.token_expires

    def __authenticate(self, email: str, password: str) -> [str, str, requests.Response]:
        """
        try the authentication request with fetched csrf and requestId payload
        :param email: stihl webapp login email non-url-encoded
        :param password: stihl webapp login password
        :return: the newly created access token, and expire time besides the legacy response
        """
        self.__fetch_new_csrf_token_and_request_id()
        url = f"{IMOW_OAUTH_URI}/authentication/authenticate/?lang=de"
        encoded_mail = quote(email)
        payload = f'mail={encoded_mail}&password={password}&csrf-token={self.csrf_token}&requestId={self.requestId}'
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        response = self.api_request(url, "POST", payload=payload, headers=headers)
        if not response.status_code == http.HTTPStatus.OK:
            logger.error(f"Authenticate: {response.status_code} {response.reason}")
            raise ConnectionError(f"{response.status_code} {response.reason}")

        response_url_query_args = furl(response.url).fragment.args
        if "access_token" not in response_url_query_args:
            raise LoginError("STIHL iMow did not return an access_token, check your credentials")

        self.access_token = response_url_query_args["access_token"]
        self.token_expires = datetime.now() + timedelta(seconds=int(response_url_query_args["expires_in"]))
        return self.access_token, self.token_expires, response

    def __fetch_new_csrf_token_and_request_id(self) -> [str, str]:
        """
        Fetch a new csrf_token and requestId to do the authentication as expected by the api
        csrf_token and requestId are used as payload within authentication
        """

        # URL needs whole redirect query parameter
        url = f"{IMOW_OAUTH_URI}/authentication/?lang=de_DE&authorizationRedirectUrl=https%3A%2F%2Foauth2" \
              ".imow.stihl.com%2Fauthorization%2F%3Fresponse_type%3Dtoken%26client_id%3D9526273B-1477-47C6-801C" \
              "-4356F58EF883%26redirect_uri%3Dhttps%253A%252F%252Fapp.imow.stihl.com%252F%2523%252Fauthorize%26state"

        response = self.api_request(url, "GET")

        soup = BeautifulSoup(response.text, 'html.parser')
        try:
            upstream_csrf_token = soup.find("input", {'name': 'csrf-token'}).get('value')
            upstream_request_id = soup.find("input", {'name': 'requestId'}).get('value')
        except AttributeError:
            raise ProcessLookupError("Did not found necessary csrf token and/or request id in html source")

        self.csrf_token = upstream_csrf_token
        self.requestId = upstream_request_id
        logger.debug("CSRF: new token and request id <Redacted>")
        return self.csrf_token, self.requestId

    def api_request(self, url, method, payload=None, headers=None) -> requests.Response:
        """
        Do a standardized request against the stihl imow webapi, with predefined headers
        :param url: The target URL
        :param method: The Method to use
        :param payload: optional payload
        :param headers: optional update headers
        :return: the requests.Response
        """
        if not self.http_session:
            self.http_session = requests.Session()

        if payload is None:
            payload = {}

        headers_obj = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de,en-US;q=0.7,en;q=0.3',
            'Authorization': f'Bearer {self.access_token if self.access_token else ""}',
            'Origin': 'https://app.imow.stihl.com',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Referer': 'https://app.imow.stihl.com/',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'TE': 'Trailers',
            'Content-Type': 'application/json'
        }
        if headers:
            headers_obj.update(headers)

        response = self.http_session.request(method, url, headers=headers_obj, data=payload)
        self.http_session.close()
        if response.status_code not in (http.HTTPStatus.OK, http.HTTPStatus.CREATED, http.HTTPStatus.ACCEPTED):
            logger.error(f"API Request: failed {response.status_code} {response.reason}")
            raise ConnectionError(f"{response.status_code} {response.reason}")
        else:
            return response

    def intent(self, imow_action: IMowActions, mower_name: str = "", mower_id: str = "", mower_action_id: str = "",
               startpoint: any = "0",
               duration: int = 30):
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
            raise AttributeError("Need some mower to work on. Please specify mower_[name|id|action_id]")
        if not mower_action_id and mower_name:
            mower_action_id = self.get_mower_action_id_from_name(mower_name)
        if not mower_action_id and mower_id:
            mower_action_id = self.get_mower_action_id_from_id(mower_id)

        if len(mower_action_id) < 16:
            raise AttributeError(
                f"Invalid mower_action_id, need exactly 16 chars, got {len(mower_action_id)} in {mower_action_id}")

        url = f"{IMOW_API_URI}/mower-actions/"

        action_value = f"{mower_action_id},{str(int(duration / 10))},{str(startpoint)}" \
            if imow_action == IMowActions.START_MOWING else mower_action_id

        action_object = {
            "actionName": imow_action.value,
            "actionValue": action_value
            # "0000000123456789,15,0" <MowerExternalId,DurationInMunitesDividedBy10,StartPoint>
        }
        logger.debug(f"Intend: {action_object}")

        payload = json.dumps(action_object)

        response = self.api_request(url, "POST", payload=payload)
        if not response.status_code == http.HTTPStatus.CREATED:
            raise ConnectionError(f"{response.status_code} {response.reason}")
        else:
            logger.debug(f'Sent mower {mower_action_id} to {imow_action}')
            return response

    def get_status_by_name(self, mower_name: str) -> dict:
        logger.debug(f"get_status_by_name: {mower_name}")
        for mower in self.receive_mowers():
            if mower.name == mower_name:
                return mower.status
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    def get_status_by_id(self, mower_id=(str, int)) -> dict:
        if not type(mower_id) == str:
            mower_id = str(mower_id)
        logger.debug(f"get_status_by_id: {mower_id}")
        try:
            return self.receive_mower_by_id(mower_id).status
        except ConnectionError:
            raise LookupError(f"Mower with id {mower_id} not found in upstream")

    def get_status_by_action_id(self, mower_action_id: str) -> dict:
        logger.debug(f"get_status_by_action_id: {mower_action_id}")
        for mower in self.receive_mowers():
            if mower.externalId == mower_action_id:
                return mower.status
        raise LookupError(f"Mower with externalId {mower_action_id} not found in upstream")

    def get_mower_action_id_from_name(self, mower_name: str) -> str:
        logger.debug(f"get_mower_action_id_from_name: {mower_name}")
        for mower in self.receive_mowers():
            if mower.name == mower_name:
                return mower.externalId
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    def get_mower_action_id_from_id(self, mower_id: str) -> str:
        logger.debug(f"get_mower_action_id_from_id: {mower_id}")
        try:
            return self.receive_mower_by_id(mower_id).externalId
        except ConnectionError:
            raise LookupError(f"Mower with id {mower_id} not found in upstream")

    def get_mower_id_from_name(self, mower_name: str) -> str:
        logger.debug(f"get_mower_id_from_name: {mower_name}")
        for mower in self.receive_mowers():
            if mower.name == mower_name:
                return mower.id
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    def receive_mowers(self) -> list[MowerState]:
        logger.debug(f"receive_mowers:")
        mowers = []
        for mower in json.loads(self.api_request(f"{IMOW_API_URI}/mowers/", "GET").text):
            mowers.append(MowerState(mower, self))
        logger.debug(mowers)
        return mowers

    def receive_mower_by_name(self, mower_name: str) -> MowerState:
        logger.debug(f"get_mower_from_name: {mower_name}")
        for mower in self.receive_mowers():
            if mower.name == mower_name:
                logger.debug(mower)
                return mower
        raise LookupError(f"Mower with name {mower_name} not found in upstream")

    def receive_mower_by_id(self, mower_id: str) -> MowerState:
        logger.debug(f"receive_mower: {mower_id}")
        mower = MowerState(
            json.loads(self.api_request(f"{IMOW_API_URI}/mowers/{mower_id}/", "GET").text), self)
        logger.debug(mower)
        return mower

    def receive_mower_current_task(self, mower_id: str) -> [MowerTask, int]:
        logger.debug(f"receive_mower_current_state: {mower_id}")
        state = MowerState(json.loads(
            self.api_request(f"{IMOW_API_URI}/mowers/{mower_id}/", "GET").text),
            self)
        logger.debug(state)
        try:
            return MowerTask(state.status.get("mainState"))
        except ValueError as ve:
            logger.warning(f'{state.status.get("mainState")} is not yet a known MowerTask-id to this Class.')
            return state.status.get("mainState")

    def receive_mower_statistics(self, mower_id: str) -> dict:
        logger.debug(f"receive_mower_statistics: {mower_id}")
        stats = json.loads(self.api_request(f"{IMOW_API_URI}/mowers/{mower_id}/statistic/", "GET").text)
        logger.debug(stats)
        return stats

    def receive_mower_week_mow_time_in_hours(self, mower_id: str) -> dict:
        logger.debug(f"receive_mower_week_mow_time_in_hours: {mower_id}")
        mow_times = json.loads(
            self.api_request(f"{IMOW_API_URI}/mowers/{mower_id}/statistics/week-mow-time-in-hours/",
                             "GET").text)
        logger.debug(mow_times)
        return mow_times

    def receive_mower_start_points(self, mower_id: str) -> dict:
        logger.debug(f"receive_mower_start_points: {mower_id}")
        start_points = json.loads(
            self.api_request(f"{IMOW_API_URI}/mowers/{mower_id}/start-points/", "GET").text)
        logger.debug(start_points)
        return start_points
