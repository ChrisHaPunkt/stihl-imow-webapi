from enum import Enum


class MowerTask(Enum):
    EDGE_MOWING = 5
    INSIDE_DOCK_NO_CHARGING = 6
    INSIDE_DOCK_CHARGING = 7
    DRIVING_TO_DOCK = 11
