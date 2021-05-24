#!/usr/bin/env python3
import unittest

from imow.api import IMowApi

TOKEN = "xx508xx63817x752xx74004x30705xx92x58349x5x78f5xx34xxxxx51"
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
