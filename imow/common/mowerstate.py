from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from imow.common.actions import IMowActions
from imow.common.exceptions import MessageNotFoundError

if TYPE_CHECKING:
    from imow.api import IMowApi

logger = logging.getLogger("imow")

# Keys from the upstream payload that must never overwrite internal attributes
# (``imow`` is the back-reference to the client; the message fields are derived).
_RESERVED_ATTRIBUTES = frozenset(
    {"imow", "stateMessage", "machineError", "machineState"}
)

# Value used for ``machineState`` when the upstream status code is unknown, so a
# single new firmware code does not break the whole poll.
_UNKNOWN_MACHINE_STATE = "UNKNOWN"


class MowerState:
    """Wraps an upstream mower payload and exposes its fields as attributes.

    Every key in the upstream dict becomes an attribute (spaces replaced by
    underscores). Because the attribute set is data-driven, referencing a field
    the upstream did not return raises :class:`AttributeError`; guard optional
    fields at the call site.

    The declarations below are **annotation-only** (no runtime value): they
    document the known payload fields and give type checkers/IDEs an interface,
    without creating misleading class-level defaults.
    """

    # --- Known upstream payload fields (populated dynamically) --------------
    accountId: str
    asmEnabled: bool
    automaticModeEnabled: bool
    boundryOffset: int
    childLock: bool
    circumference: int
    cModuleId: str
    codePage: int
    coordinateLatitude: float
    coordinateLongitude: float
    corridorMode: int
    demoModeEnabled: bool
    deviceType: int
    deviceTypeDescription: str
    edgeMowingMode: int
    endOfContract: str
    energyMode: int
    externalId: str
    firmwareVersion: str
    gdprAccepted: bool
    gpsProtectionEnabled: bool
    id: str
    imsi: str
    lastWeatherCheck: str
    ledStatus: int
    localTimezoneOffset: int
    mappingIntelligentHomeDrive: int
    mowerImageThumbnailUrl: str
    mowerImageUrl: str
    name: str
    protectionLevel: int
    rainSensorMode: int
    smartLogic: Dict[str, Any]
    softwarePacket: str
    status: Dict[str, Any]
    team: Any
    teamable: bool
    timeZone: str
    unitFormat: int
    version: str

    ERROR_MAINSTATE_CODE = 1

    def __init__(self, upstream: dict, imow: "IMowApi") -> None:
        self.imow = imow

        self.stateMessage: Dict[str, Any] = {
            "short": "",
            "long": "",
            "legacyMessage": "",
            "errorId": "",
            "error": False,
        }
        self.machineError: Optional[str] = None
        self.machineState: Optional[str] = None
        self.replace_state(upstream)

    def replace_state(self, upstream: dict) -> None:
        """Merge an upstream payload into this instance.

        Reserved keys (see ``_RESERVED_ATTRIBUTES``) are dropped so a hostile or
        renamed upstream field cannot clobber the client back-reference or the
        derived message fields.
        """
        cleaned = {
            key.replace(" ", "_"): value
            for key, value in upstream.items()
            if key.replace(" ", "_") not in _RESERVED_ATTRIBUTES
        }
        self.__dict__.update(cleaned)
        self.update_state_messages()

    async def update_setting(self, setting: str, new_value: Any) -> None:
        await self.imow.update_setting(
            mower_id=self.id, setting=setting, new_value=new_value
        )

    def _get_state_codes(self) -> Optional[tuple[int, bool]]:
        """Return ``(short_code, is_error)`` from ``status``, or ``None``.

        Returns ``None`` (rather than raising) if the payload lacks a usable
        ``status`` block, so message resolution degrades gracefully.
        """
        status = getattr(self, "status", None)
        if not isinstance(status, dict) or "mainState" not in status:
            logger.debug("MowerState has no usable 'status'; skipping messages")
            return None
        is_error = status["mainState"] == self.ERROR_MAINSTATE_CODE
        short_code = status["extraStatus"] if is_error else status["mainState"]
        return short_code, is_error

    def update_state_messages(self) -> None:
        codes = self._get_state_codes()
        if codes is None or self.imow.messages_user is None:
            if codes is None:
                logger.debug("MowerState has no usable 'status'; state UNKNOWN")
            else:
                logger.debug("i18n messages not loaded yet; skipping state messages")
            # Still derive a (neutral) machineState so it is never left as None.
            self.generate_machine_state()
            return
        short_code, is_error = codes
        messages = self.imow.messages_user

        try:
            if not is_error:
                (
                    self.stateMessage["short"],
                    self.stateMessage["long"],
                ) = messages.get_status_message(short_code=short_code)
                self.stateMessage["error"] = False
                self.machineError = None
                self.stateMessage["errorId"] = ""
            else:
                (
                    self.stateMessage["short"],
                    self.stateMessage["long"],
                    self.stateMessage["errorId"],
                    self.stateMessage["legacyMessage"],
                ) = messages.get_error_message(short_code=short_code)
                self.stateMessage["error"] = True
                self.machineError = self.stateMessage["errorId"]
        except MessageNotFoundError as err:
            logger.warning("Unknown mower state/error code: %s", err)
        self.generate_machine_state()

    def generate_machine_state(self) -> None:
        codes = self._get_state_codes()
        if codes is None or self.imow.messages_en is None:
            self.machineState = _UNKNOWN_MACHINE_STATE
            return
        short_code, is_error = codes
        messages = self.imow.messages_en

        try:
            if not is_error:
                state_msg_short, _ = messages.get_status_message(short_code=short_code)
            else:
                (
                    state_msg_short,
                    _long,
                    _error_id,
                    _legacy,
                ) = messages.get_error_message(short_code=short_code)
        except MessageNotFoundError:
            self.machineState = _UNKNOWN_MACHINE_STATE
            return

        self.machineState = state_msg_short.upper().replace(" ", "_").replace(".", "")

    async def update_from_upstream(self) -> "MowerState":
        response = await self.imow.receive_mower_by_id(self.id)
        self.replace_state(response.__dict__)
        return self

    def get_current_task(self) -> str:
        return self.stateMessage["short"]

    async def get_current_status(self) -> dict:
        await self.update_from_upstream()
        return self.status

    async def get_from_upstream(self) -> "MowerState":
        return await self.update_from_upstream()

    async def get_statistics(self) -> dict:
        return await self.imow.receive_mower_statistics(self.id)

    async def get_startpoints(self) -> list:
        return await self.imow.receive_mower_start_points(self.id)

    async def get_mower_week_mow_time_in_hours(self) -> dict:
        return await self.imow.receive_mower_week_mow_time_in_hours(self.id)

    async def intent(
        self,
        imow_action: IMowActions,
        first_action_value_param: Any = "",
        second_action_value_param: Any = "",
        test_mode: bool = False,
        **kwargs: Any,
    ) -> None:
        await self.imow.intent(
            imow_action=imow_action,
            first_action_value_param=first_action_value_param,
            second_action_value_param=second_action_value_param,
            mower_external_id=self.externalId,
            test_mode=test_mode,
            **kwargs,
        )
