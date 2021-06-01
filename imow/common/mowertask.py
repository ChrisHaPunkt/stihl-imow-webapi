from enum import Enum


class MowerTask(Enum):
    # Common
    STANDBY = 0

    # Mowing States
    EDGE_MOWING = 5

    # Dock Relations
    INSIDE_DOCK_NO_CHARGING = 6
    INSIDE_DOCK_CHARGING = 7
    DRIVING_TO_DOCK = 11

    # Errors
    DOCK_ERROR = 1
