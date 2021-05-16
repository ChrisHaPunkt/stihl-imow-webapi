#!/usr/bin/env python3
import unittest

from imow.api import IMowApi
from imow.common.currentmowerstate import CurrentMowerState, MowerTaskState

TOKEN = 'xx508xx63817x752xx74004x30705xx92x58349x5x78f5xx34xxxxx51'
MOWER_NAME = "MyMower"
MOWER_ACTION_ID = "0000000123456789"
MOWER_ID = "12345"


class TestIMowApiUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.imow = IMowApi(token=TOKEN)
        cls.initialized = True

    def setUp(self) -> None:
        if not self.initialized:
            self.imow = IMowApi(token=TOKEN)

    def test_auth_without_anything(self):
        with self.assertRaises(LookupError, msg="Expected API to raise when instancing without credentials"):
            IMowApi()

    def test_unknown_mower_state(self):
        result = CurrentMowerState(dict())
        result.status["mainState"] = 123
        self.assertIsInstance(result.get_current_taskstate(), int, msg="Expected Mower class returned int(123)")
        self.assertEqual(result.get_current_taskstate(), 123, msg="Expected Mower class returned int(123)")

    def test_known_mower_state(self):
        result = CurrentMowerState(dict())
        result.status["mainState"] = 7
        self.assertIsInstance(result.get_current_taskstate(), MowerTaskState, msg="Expected Mower class returned int(123)")
        self.assertEqual(result.get_current_taskstate(), MowerTaskState.INSIDE_DOCK_CHARGING,
                         msg="Expected Mower class returned MowerState.INSIDE_DOCK_CHARGING")
