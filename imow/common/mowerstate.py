import logging

from imow.common.actions import IMowActions

logger = logging.getLogger("imow")


class MowerState:
    ERROR_MAINSTATE_CODE = 1

    def __init__(self, upstream: dict, imow):  # Type: api: IMowApi
        self.imow = imow

        self.stateMessage = {
            "short": "",
            "long": "",
            "legacyMessage": "",
            "errorId": "",
            "error": False,
        }
        self.machineError = None
        self.machineState = None
        self.replace_state(upstream)

    def replace_state(self, upstream: dict):
        self.__dict__.update(
            map(lambda kv: (kv[0].replace(" ", "_"), kv[1]), upstream.items())
        )
        self.update_state_messages()

    async def update_setting(self, setting, new_value):
        await self.imow.update_setting(
            mower_id=self.id, setting=setting, new_value=new_value
        )

    def update_state_messages(self):

        if self.status["mainState"] != self.ERROR_MAINSTATE_CODE:
            (
                self.stateMessage["short"],
                self.stateMessage["long"],
            ) = self.imow.messages_user.get_status_message(
                short_code=self.status["mainState"]
            )

            # Reset error indication
            self.stateMessage["error"] = False
            self.machineError = None
            self.stateMessage["errorId"] = ""

        else:

            (
                self.stateMessage["short"],
                self.stateMessage["long"],
                self.stateMessage["errorId"],
                self.stateMessage["legacyMessage"],
            ) = self.imow.messages_user.get_error_message(
                short_code=self.status["extraStatus"]
            )
            # Set error indication to true
            self.stateMessage["error"] = True
            self.machineError = self.stateMessage["errorId"]
        self.generate_machine_state()

    def generate_machine_state(self):
        if self.status["mainState"] != self.ERROR_MAINSTATE_CODE:
            (
                state_msg_short,
                state_msg_long,
            ) = self.imow.messages_en.get_status_message(
                short_code=self.status["mainState"]
            )
        else:
            (
                state_msg_short,
                state_msg_long,
                errorId,
                legacyMessage,
            ) = self.imow.messages_en.get_error_message(
                short_code=self.status["extraStatus"]
            )
        cleaned_msg = (
            state_msg_short.upper().replace(" ", "_").replace(".", "")
        )
        self.machineState = cleaned_msg

    async def update_from_upstream(self):
        response = await self.imow.receive_mower_by_id(self.id)
        self.replace_state(response.__dict__)
        return self

    def get_current_task(self) -> str:
        return self.stateMessage["short"]

    async def get_current_status(self) -> dict:
        await self.update_from_upstream()
        return self.status

    async def get_from_upstream(self):  # Type: MowerState
        return await self.update_from_upstream()

    async def get_statistics(self) -> dict:
        return await self.imow.receive_mower_statistics(self.id)

    async def get_startpoints(self) -> dict:
        return await self.imow.receive_mower_start_points(self.id)

    async def get_mower_week_mow_time_in_hours(self) -> dict:
        return await self.imow.receive_mower_week_mow_time_in_hours(self.id)

    async def intent(
        self,
        imow_action: IMowActions,
        startpoint: any = "0",
        duration: int = 30,
    ) -> None:
        response = await self.imow.intent(
            imow_action=imow_action,
            startpoint=startpoint,
            duration=duration,
            mower_external_id=self.externalId,
        )

    accountId: str = {str}
    asmEnabled: bool = {bool}
    automaticModeEnabled: bool = {bool}
    boundryOffset: bool = {int}  # 60
    childLock: bool = {bool}  # False
    circumference: bool = {int}  # 41
    cModuleId: str = {str}  # '0234d0fffab1d345'
    codePage: bool = {int}  # 0
    coordinateLatitude: float = {float}  # 54.123456
    coordinateLongitude: float = {float}  # 10.654321
    corridorMode: bool = {int}  # 0
    demoModeEnabled: bool = {bool}  # False
    deviceType: bool = {int}  # 24
    deviceTypeDescription: str = {str}  # 'RMI 422 PC'
    edgeMowingMode: bool = {int}  # 2
    endOfContract: str = {str}  # '2000-01-01T01:59:43+00:00'
    energyMode: bool = {int}  # 3
    externalId: str = {str}  # '0000000123456789'
    firmwareVersion: str = {str}  # '01v013'
    gdprAccepted: bool = {bool}  # True
    gpsProtectionEnabled: bool = {bool}  # True
    id: str = {str}  # '31466'
    imsi: str = {str}  # '16198732186461'
    lastWeatherCheck: str = {str}  # '2021-05-15T01:42:25+00:00'
    ledStatus: bool = {int}  # 11
    localTimezoneOffset: bool = {int}  # 7182
    mappingIntelligentHomeDrive: bool = {int}  # 0
    mowerImageThumbnailUrl = {
        str
    }  # 'https://app-cdn-appdata001-r-euwe-1b3d32.azureedge.net/device-images/mower-images/31466-2309868077
    # -thumb.png'
    mowerImageUrl = {
        str
    }  # 'https://app-cdn-appdata001-r-euwe-1b3d32.azureedge.net/device-images/mower-images/31466-2309868077
    # -photo.png'
    name: str = {str}  # 'Mährlin'
    protectionLevel: bool = {int}  # 1
    rainSensorMode: bool = {int}  # 1
    smartLogic: dict = {dict: 13}
    # {'dynamicMowingplan': False, 'mower': None, 'mowingArea': 100, 'mowingAreaInFeet': 1000, 'mowingAreaInMeter': 100,
    # 'mowingGrowthAdjustment': 0, 'mowingTime': 60, 'mowingTimeManual': False, 'performedActivityTime': 3,
    # 'smartNotifications': False, 'suggestedActivityTime': 135, 'totalActivityActiveTime': 0,
    # 'weatherForecastEnabled': True}
    softwarePacket: str = {str}  # '12.03'
    status: dict = {dict: 15}
    # {'bladeService': False, 'chargeLevel': 66, 'extraStatus': 0, 'extraStatus1': 0, 'extraStatus2': 0,
    # 'extraStatus3': 0, 'extraStatus4': 0, 'extraStatus5': 0, 'lastGeoPositionDate': '2021-05-15T07:12:10+00:00',
    # 'lastNoErrorMainState': 7, 'lastSeenDate': '2021-05-13T23:58:31+00:00', 'mainState': 7, 'mower': None,
    # 'online': True, 'rainStatus': False}
    team = {None}  # None
    teamable: bool = {bool}  # False
    timeZone: str = {str}  # 'Europe/Berlin'
    unitFormat: bool = {int}  # 0
    version: str = {str}  # '3.2.038'
