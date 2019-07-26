import socket, threading, select

from . import constants as c

class WebsocketSession:
    def __init__(self, sock=None, address=None):
        self.sock = sock
        self.address = address
        self.state = c.StateUnconnected
        self._recv_buffer = ""

class WebsocketServer:
    def __init__(self, address="0.0.0.0", port=8080):
        self.address = address
        self.port = port
        self.socket = None
        self.thread = None
        self.sessions = []
    def listen(self):
        self.socket = socket.socket()
        self.socket.bind((self.address, self.port))
        self.socket.listen(1)
        self.thread = threading.Thread(target=self._threadfn)
        self.thread.start()
    def _threadfn(self):
        while True:
            rlist, wlist, elist = self.socket.select([self.socket], [], [self.socket], 1)
            for item in rlist:
                if item == self.socket:
                    sock, addr = item.accpet()
                    sock.setblocking(0)
                    sess = WebsocketSession(sock, addr)
                    sess.state = c.StateConnecting
                    self.sessions.append(sess)
                else:
                    sess = list(filter(lambda x: x.sock == item, self.sessions))
                    if len(sess) == 0: continue
                    sess = sess[0]
                    if (sess.state == c.StateConnecting):
                        while True:
                            try:
                                data += item.recv(1024)
                            except socket.error as e:
                                break



