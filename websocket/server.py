import socket, threading, select, re, hashlib, base64, multiprocessing

from . import constants as c
from .frame import WebsocketFrame
import socketio as io

class WebsocketSession:
    def __init__(self, sock=None, address=None, buffer_size=1024):
        self._sock = sock
        self._address = address
        self._dirty_data = b""
        self._recving_frame = None
        self._reset()
    def _reset(self):
        self._state = c.StateUnconnected
        self._reqline = None
        self._headers = {}
    def _complete_frame(self):
        # TODO: assemble the frame or emit an event
        self._recving_frame = None
    @property
    def state(self):
        return self._state
    def close(self):
        self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()
        self._state = c.StateClosed

class WebsocketServer:
    # buffer_size: maximum buffer size for receiving HTTP headers
    def __init__(self, buffer_size=1024):
        self._address = None
        self._port = None
        self._socket = None
        self._thread = None
        self._pipefd1 = None # self-pipe trick
        self._pipefd2 = None # self-pipe trick
        self._sessions = []
        self._buffer_size = buffer_size
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
            rlist, _, _ = select.select(srlist, swlist, srlist + swlist, 1)
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
                    self._sessions.append(sess)
                else:
                    # a client has sent some data to us
                    sess = list(filter(lambda x: x._sock == item, self._sessions))
                    if len(sess) == 0: continue
                    sess = sess[0]
                    # If we are in Unconnected State, we attempt to parse the first line as a HTTP request line.
                    # HTTP request line format:
                    #     <method> <url> HTTP/<version>
                    # Note that method must be 'GET'.
                    # Note that this loop will be executed at most once (we just use `while` to substitute `if` for convenient flow-control).
                    # If we enter this block and exit from this state, _dirty_data should be cleared at the time we exit.
                    recved_bytes = 0
                    while sess._state == c.StateUnconnected:
                        line = io.recv_line(sess._sock, self._buffer_size, _dirty_data=sess._dirty_data)
                        recved_bytes += len(line) - len(sess._dirty_data)
                        if io.error == io.e.ErrorBufferOverflow:
                            sess._dirty_data = line
                            sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
                            break
                        elif io.error == io.e.ErrorStreamEmpty:
                            sess._dirty_data = line
                            break
                        sess._dirty_data = sess._dirty_data[len(line):]
                        try:
                            line = line.decode("ascii")
                        except UnicodeError:
                            sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
                            break
                        line = re.split(r"\s+", line.strip())
                        if len(line) < 3:
                            sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
                            break
                        if line[0].upper() != "GET":
                            sess._sock.send("HTTP/1.1 405 Method Not Allowed\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
                            break
                        sess._state = c.StateConnecting
                        break
                    # If we are in Connecting State, we attempt to parse each line as a HTTP header line until an empty line is met.
                    # If we enter this block and exit from this state, _dirty_data should be cleared at the time we exit.
                    while sess._state == c.StateConnecting:
                        line = io.recv_line(sess._sock, self._buffer_size, _dirty_data=sess._dirty_data)
                        recved_bytes += len(line) - len(sess._dirty_data)
                        if io.error == io.e.ErrorBufferOverflow:
                            sess._dirty_data = line
                            sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
                            break
                        elif io.error == io.e.ErrorStreamEmpty:
                            sess._dirty_data = line
                            break
                        sess._dirty_data = sess._dirty_data[len(line):]
                        try:
                            line = line.decode("ascii")
                        except UnicodeError:
                            sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
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
                                sess.close()
                                self._sessions.remove(sess)
                            break
                        colonidx = line.find(":")
                        if colonidx <= 0:
                            sess._sock.send("HTTP/1.1 400 Bad Request\r\n\r\n")
                            sess.close()
                            self._sessions.remove(sess)
                            break
                        header_key = line[:colonidx].strip()
                        header_value = line[colonidx+1:].strip()
                        sess._headers[header_key] = header_value
                        break
                    # If we are in Connected State, we parse data with websocket protocol.
                    # Note that this loop will be executed at most once (we just use `while` to substitute `if` for convenient flow-control).
                    while sess._state == c.StateConnected:
                        # if recving_frame is not present, create a new frame
                        if sess._recving_frame is None:
                            sess._recving_frame = WebsocketFrame()
                        frame = sess._recving_frame
                        # Get frame header fields.
                        # For each field, after the time that we have read all its bytes, _dirty_data should be empty.
                        if frame._field_flags_opcode is None:
                            data = io.recv_bytes(sess._sock, 1, _dirty_data=sess._dirty_data)
                            recved_bytes += len(data) - len(sess._dirty_data)
                            if io.error == io.e.ErrorStreamEmpty:
                                sess._dirty_data = data
                                break
                            sess._dirty_data = sess._dirty_data[len(data):]
                            frame._field_flags_opcode = data
                        if frame._field_mask_len is None:
                            data = io.recv_bytes(sess._sock, 1, _dirty_data=sess._dirty_data)
                            recved_bytes += len(data) - len(sess._dirty_data)
                            if io.error == io.e.ErrorStreamEmpty:
                                sess._dirty_data = data
                                break
                            sess._dirty_data = sess._dirty_data[len(data):]
                            frame._field_mask_len = data
                        if frame.payload_length is None and frame._field_len2 is None:
                            data = io.recv_bytes(sess._sock, 2, _dirty_data=sess._dirty_data)
                            recved_bytes += len(data) - len(sess._dirty_data)
                            if io.error == io.e.ErrorStreamEmpty:
                                sess._dirty_data = data
                                break
                            sess._dirty_data = sess._dirty_data[len(data):]
                            frame._field_len2 = data
                        if frame.payload_length is None and frame._field_len6 is None:
                            data = io.recv_bytes(sess._sock, 6, _dirty_data=sess._dirty_data)
                            recved_bytes += len(data) - len(sess._dirty_data)
                            if io.error == io.e.ErrorStreamEmpty:
                                sess._dirty_data = data
                                break
                            sess._dirty_data = sess._dirty_data[len(data):]
                            frame._field_len6 = data
                        if frame.flag_mask and frame._field_maskkey is None:
                            data = io.recv_bytes(sess._sock, 4, _dirty_data=sess._dirty_data)
                            recved_bytes += len(data) - len(sess._dirty_data)
                            if io.error == io.e.ErrorStreamEmpty:
                                sess._dirty_data = data
                                break
                            sess._dirty_data = sess._dirty_data[len(data):]
                            frame._field_maskkey = data
                        # get frame data
                        if frame._payload_buffer is None:
                            frame._payload_buffer = bytearray(frame.playload_length)
                            frame._payload_bytesrecved = 0
                        if len(sess._dirty_data) > 0:
                            cp_start = frame._payload_bytesrecved
                            cp_end = max(frame._payload_bytesrecved + len(sess._dirty_data), len(frame._payload_buffer))
                            cp_len = cp_end - cp_start
                            memoryview(frame._payload_buffer)[cp_start:cp_end] = sess._dirty_data[:cp_len]
                            sess._dirty_data = sess._dirty_data[cp_len:]
                            frame._payload_bytesrecved = cp_end
                        if frame._payload_bytesrecved < len(frame._payload_buffer):
                            cp_len = len(frame._payload_buffer) - frame._payload_bytesrecved
                            recved_bytes += sess._sock.recv_into(memoryview(frame._payload_buffer)[frame._payload_bytesrecved:], cp_len)
                        if frame._payload_bytesrecved == len(frame._payload_buffer):
                            sess._complete_frame()
                        break
                    # All jobs for this client event are done.
                    # If no bytes are received during handling this event, the socket should be closed.
                    if recved_bytes == 0:
                        sess.close()
                        self._sessions.remove(sess)






