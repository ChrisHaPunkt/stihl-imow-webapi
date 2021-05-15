#!/usr/bin/env python3
import http
import unittest
import json

from imow.api import IMowApi
from imow.common.actions import IMowActions
from imow.common.mower import Mower, MowerState
from secrets import *

import logging

logger = logging.getLogger('imow')
logger.setLevel(logging.DEBUG)


class TestIMowApiOnlineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.imow = IMowApi(EMAIL, PASSWORD)
        cls.test_mower = cls.imow.receive_mower_by_name(MOWER_NAME)
        cls.initialized = True

    def setUp(self) -> None:
        if not self.initialized:
            self.imow = IMowApi(EMAIL, PASSWORD)

    def test_auth_with_email_and_password(self):
        token_old = self.imow.access_token
        token_new, expire_time = self.imow.get_token(EMAIL, PASSWORD, force_reauth=True)
        self.assertIs(len(token_new), 98, msg="Expected new token has 98 chars")
        self.assertNotEqual(token_old, token_new, msg="Expected old and new token differ")

    def test_get_mowers(self):
        result = self.imow.receive_mowers()
        self.assertIsInstance(result, list, msg="Expected array with mowers returned")

    def test_get_mower(self):
        result = self.imow.receive_mower_by_id(mower_id=self.test_mower.id)
        self.assertIsInstance(result, Mower, msg="Expected Mower class returned")

    def test_get_status_by_name(self):
        result = self.imow.get_status_by_name(MOWER_NAME)
        self.assertTrue(result["online"], msg="Expected 200 HTTP Error Code")

    def test_get_status_by_wrong_id(self):
        with self.assertRaises(LookupError):
            result = self.imow.get_status_by_id(mower_id=int(self.test_mower.id) + 1)

    def test_intent_to_dock_by_id(self):
        result = self.imow.intent(IMowActions.TO_DOCKING, mower_id=self.test_mower.id)
        self.assertIs(result.status_code, int(http.HTTPStatus.CREATED), msg="Expected 201 HTTP Code")

    def test_intent_start_mowing(self):
        result = self.imow.intent(IMowActions.START_MOWING, mower_id=self.test_mower.id, duration=60, startpoint=2)
        self.assertIs(result.status_code, int(http.HTTPStatus.CREATED), msg="Expected 201 HTTP Code")
        self.assertEqual("6,2", json.loads(result.request.body)["actionValue"][-3:])

    def test_intent_start_mowing_with_defaults(self):
        result = self.imow.intent(IMowActions.START_MOWING, mower_id=self.test_mower.id)
        self.assertIs(result.status_code, int(http.HTTPStatus.CREATED), msg="Expected 201 HTTP Code")
        self.assertEqual("3,0", json.loads(result.request.body)["actionValue"][-3:])

    def test_intent_to_dock_by_name(self):
        result = self.imow.intent(IMowActions.TO_DOCKING, self.test_mower.name)
        self.assertIs(result.status_code, int(http.HTTPStatus.CREATED), msg="Expected 201 HTTP Code")

    def test_intent_to_dock_by_mower_action_id(self):
        result = self.imow.intent(IMowActions.TO_DOCKING, mower_action_id=self.test_mower.externalId)
        self.assertIs(result.status_code, int(http.HTTPStatus.CREATED), msg="Expected 201 HTTP Code")

    def test_mower_state(self):
        result = self.imow.receive_mower_current_state(mower_id=self.test_mower.id)
        self.assertIsInstance(result, MowerState, msg="Expected MowerState class returned")