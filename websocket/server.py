import socket, threading, select, re, hashlib, base64, multiprocessing

from . import constants as c
from .frame import WebsocketFrame

class WebsocketSession:
    def __init__(self, sock=None, address=None, buffer_size=1024):
        self._sock = sock
        self._address = address
        self._recv_buffer = bytearray(buffer_size)
        self._recv_buffer_length = 0
        self._recv_data = bytes()
        self._recving_frame = None
        self._reset()
    def _reset(self):
        self._state = c.StateUnconnected
        self._reqline = None
        self._headers = {}
    def _reset_recv_buffer(self):
        self._recv_buffer_length = 0
    # left shift _recv_buffer
    def _shift_recv_buffer(self, amount):
        if (amount >= self._recv_buffer_length):
            self._recv_buffer_length = 0
        else:
            self._recv_buffer[:self._recv_buffer_length-amount] = self._recv_buffer[amount:self._recv_buffer_length]
    @property
    def _recv_buffer_readable(self):
        return memoryview(self._recv_buffer)[:self._recv_buffer_length]
    @property
    def _recv_buffer_writable(self):
        return memoryview(self._recv_buffer)[self._recv_buffer_length:]
    # _get_line: pop the first line from the _recv_buffer
    #            if we cannot detect a CR-LF, None is returned
    def _get_line(self):
        idx = self._recv_buffer.find(b"\r\n", 0, self._recv_buffer_length)
        if idx < 0:
            return None
        elif idx == 0:
            self._shift_recv_buffer(2)
            return b""
        else:
            line = bytes(self._recv_buffer[0:idx])
            self._shift_recv_buffer(idx+2)
            return line
    # _get_bytes: pop N bytes from the _recv_buffer
    #             if there are not enough bytes available, None is returned
    #             but if greedy is set True, as much bytes as we can get will be popped
    def _get_bytes(self, nbytes=None, greedy=False):
        if nbytes is None or self._recv_buffer_length < nbytes:
            if greedy:
                thebytes = self._recv_buffer[0:self._recv_buffer_length]
                self._shift_recv_buffer(self._recv_buffer_length)
                return thebytes
            else:
                return None
        else:
            thebytes = self._recv_buffer[0:nbytes]
            self._shift_recv_buffer(nbytes)
            return thebytes
    @property
    def state(self):
        return self._state
    def close(self):
        self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()

class WebsocketServer:
    def __init__(self, ):
        self._address = None
        self._port = None
        self._socket = None
        self._thread = None
        self._pipefd1 = None # self-pipe trick
        self._pipefd2 = None # self-pipe trick
        self._sessions = []
    def listen(self, address="0.0.0.0", port=8080):
        self._address = address
        self._port = port
        self._socket = socket.socket()
        self._socket.bind((self._address, self._port))
        self._socket.listen(1)
        self._pipefd1, self._pipefd2 = multiprocessing.Pipe()
        self._thread = threading.Thread(target=self._threadfn)
        self._thread.start()
    def close(self):
        self._pipefd1.send("terminate")
        self._thread.join()
        for sess in self._sessions:
            sess.close()
        self._socket.close()

    @property
    def sessions(self):
        return [sess for sess in self._sessions]
    
    def _remove_session(self, sess):
        sess.close()
        self._sessions.remove(sess)

    def _threadfn(self):
        stopped = False
        while not stopped:
            srlist = [self._pipefd2, self._socket] + [sess._sock for sess in self._sessions]
            swlist = []
            rlist, wlist, elist = select.select(srlist, swlist, srlist + swlist, 1)
            for item in rlist:
                if item == self._pipefd2:
                    # self-pipe
                    stopped = True
                    break
                elif item == self._socket:
                    # a client is requesting for connecting
                    sock, addr = item.accept()
                    sock.setblocking(0)
                    sess = WebsocketSession(sock, addr)
                    sess._state = c.StateUnconnected
                    sess._reset_recv_buffer()
                    self._sessions.append(sess)
                else:
                    # a client has sent some data to us
                    sess = list(filter(lambda x: x._sock == item, self._sessions))
                    if len(sess) == 0: continue
                    sess = sess[0]
                    if sess._state == c.StateConnected:
                        pass
                    else:5
                        # receive some bytes here
                        recved_length = item.recv_into(sess._recv_buffer_writable)
                        if recved_length == 0:
                            # remote shutdown, we should shutdown here
                            self._remove_session(sess)
                            continue
                        sess._recv_buffer_length += recved_length
                        # if we are in Unconnected State, we attempt to parse the first line as a HTTP request line
                        # HTTP request line format:
                        #     <method> <url> HTTP/<version>
                        # note that method must be 'GET'
                        # note that this loop will be executed up to once (we just use `while` to substitute `if` for convenient flow-control)
                        while sess._state == c.StateUnconnected:
                            line = sess._get_line()
                            if line is None:
                                continue
                            try:
                                line = line.decode("ascii")
                            except UnicodeError:
                                sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                                sess._state = c.StateClosed
                                break
                            line = re.split(r"\s+", line.strip())
                            if len(line) < 3:
                                sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                                sess._state = c.StateClosed
                                break
                            if line[0].upper() != "GET":
                                sess._sock.send("HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                                sess._state = c.StateClosed
                                break
                            sess._state = c.StateConnecting
                            break
                        # if we are in Connecting State, we attempt to parse each line as a HTTP header line until an empty line is met
                        while sess._state == c.StateConnecting:
                            line = sess._get_line()
                            if line is None:
                                break
                            try:
                                line = line.decode("ascii")
                            except UnicodeError:
                                sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                                sess._state = c.StateClosed
                                break
                            line = line.strip()
                            if len(line) == 0:
                                # header is finished here, we have to determine if it is a valid websocket request,
                                # then response properly and establish the connection.
                                if "Connection" in sess._headers and sess._headers["Connection"].lower().strip() == "upgrade" \
                                        and "Upgrade" in sess._headers and sess._headers["Upgrade"].lower().strip() == "websocket" \
                                        and "Sec-WebSocket-Version" in sess._headers \
                                        and "Sec-WebSocket-Key" in sess._headers:
                                    seckey = sess._headers["Sec-WebSocket-Key"]
                                    secaccept = hashlib.sha1()
                                    secaccept.update(seckey.encode("ascii") + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                                    secaccept = base64.b64encode(secaccept.digest())
                                    sendstr = "HTTP/1.1 101 Switching Protocols\r\n"
                                    sendstr += "Connection: Upgrade\r\n"
                                    sendstr += "Upgrade: websocket\r\n"
                                    sendstr += "Sec-WebSocket-Accept: " + secaccept + "\r\n"
                                    sendstr += "\r\n"
                                    sess._sock.send(sendstr)
                                    sess._state = c.StateConnected
                                else:
                                    sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                                    sess._state = c.StateClosed
                                break
                            colonidx = line.find(":")
                            if colonidx <= 0:
                                sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                                sess._state = c.StateClosed
                                break
                            header_key = line[:colonidx].strip()
                            header_value = line[colonidx+1:].strip()
                            sess._headers[header_key] = header_value
                            break
                        # if we are in Connected State, we parse data with websocket protocol
                        while sess._state == c.StateConnected:
                            # if recving_frame is not present, create a new frame
                            if sess._recving_frame is None:
                                sess._recving_frame = WebsocketFrame()
                            frame = sess._recving_frame
                            # get frame header fields
                            if frame._field_flags_opcode is None:
                                frame._field_flags_opcode = frame._get_bytes(1)
                                if frame._field_flags_opcode is None:
                                    break
                            if frame._field_mask_len is None:
                                frame._field_mask_len = frame._get_bytes(1)
                                if frame._field_mask_len is None:
                                    break
                            if frame.payload_length is None and frame._field_len2 is None:
                                frame._field_len2 = frame._get_bytes(2)
                                if frame._field_len2 is None:
                                    break
                            if frame.payload_length is None and frame._field_len6 is None:
                                frame._field_len6 = frame._get_bytes(6)
                                if frame._field_len6 is None:
                                    break
                            if frame.flag_mask and frame._field_maskkey is None:
                                frame._field_maskkey = frame._get_bytes(4)
                                if frame._field_maskkey is None:
                                    break
                            # get frame data
                            if frame._payload_buffer is None:
                                frame._payload_buffer = bytearray(frame.playload_length)
                                frame._payload_bytesrecved = 0
                            sess._sock.recv_into(memoryview(frame._payload_buffer)[frame._payload_bytesrecved:], )





