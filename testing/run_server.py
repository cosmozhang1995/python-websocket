import sys, os
sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from websocket.server import WebsocketServer
import select, signal

server = WebsocketServer()
server.listen()

try:
    r,w,e = select.select([], [], [])
except KeyboardInterrupt as e:
    print("main KeyboardInterrupt")
    server.close()

