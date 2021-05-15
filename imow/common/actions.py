from enum import Enum


class IMowActions(Enum):
    EDGE_MOWING = "edgeMowing"
    TO_DOCKING = "toDocking"
    START_MOWING = "startMowingFromPoint"
