StateUnconnected = 0
StateConnecting = 1
StateConnected = 2
StageClosing = 3
StateClosed = 4

from .const import Constants

class consts(Constants):
    StateUnconnected = 0
    StateConnecting = 1
    StateConnected = 2
    StageClosing = 3
    StateClosed = 4
        
import sys
sys.modules[__name__] = consts()
