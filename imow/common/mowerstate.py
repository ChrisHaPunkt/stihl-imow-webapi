import json
import logging

from imow.common.actions import IMowActions
from imow.common.consts import IMOW_API_URI
from imow.common.mowertask import MowerTask

logger = logging.getLogger('imow')


class MowerState:

    def __init__(self, upstream: dict, api):  # Type: api: IMowApi
        self.api = api
        self.update(upstream)

    def update(self, upstream: dict = None):
        if not upstream:
            upstream = json.loads(self.api.api_request(f"{IMOW_API_URI}/mowers/{self.id}/", "GET").text)
        self.__dict__.update(map(lambda kv: (kv[0].replace(' ', '_'), kv[1]), upstream.items()))

    def get_current_task(self) -> (MowerTask, int):
        return self.api.receive_mower_current_task(mower_id=self.id)

    def intent(self, imow_action: IMowActions, startpoint: any = "0", duration: int = 30):
        self.api.intent(imow_action=imow_action, startpoint=startpoint, duration=duration,
                        mower_action_id=self.externalId)

    def get_status(self) -> dict:
        self.update()
        return self.status

    def get_statistics(self) -> dict:
        return self.api.receive_mower_statistics(self.id)

    def get_startpoints(self) -> dict:
        return self.api.receive_mower_start_points(self.id)

    def get_mower_week_mow_time_in_hours(self) -> dict:
        return self.api.receive_mower_week_mow_time_in_hours(self.id)

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
        str}  # 'https://app-cdn-appdata001-r-euwe-1b3d32.azureedge.net/device-images/mower-images/31466-2309868077
    # -thumb.png'
    mowerImageUrl = {
        str}  # 'https://app-cdn-appdata001-r-euwe-1b3d32.azureedge.net/device-images/mower-images/31466-2309868077
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
