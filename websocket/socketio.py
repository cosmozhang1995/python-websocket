from .const import Constants

class ErrorConsts(Constants):
    NoError = 0
    ErrorBufferOverflow = 1
    ErrorStreamEmpty = 2

ErrorConsts = ErrorConsts()
e = Errors = ErrorConsts

error = e.Success

def recv_line(sock, maxlen, _dirty_data=b""):
    global error
    buffer = bytearray(maxlen)
    buffer[:len(_dirty_data)] = _dirty_data
    for i in range(len(_dirty_data), len(buffer)):
        thebyte = sock.recv(1)
        if len(thebyte) == 0:
            error = e.ErrorBufferOverflow
            return bytes(buffer[:i])
        buffer[i] = thebyte
        if buffer[-2:] == b"\r\n":
            error = e.NoError
            return bytes(buffer[:i+1])
    error = e.ErrorBufferOverflow
    return bytes(buffer)

def recv_bytes(sock, len, _dirty_data=b""):
    global error
    buffer = bytearray(len)
    buffer[:len(_dirty_data)] = _dirty_data
    for i in range(len(_dirty_data), len(buffer)):
        thebyte = sock.recv(1)
        if len(thebyte) == 0:
            error = e.ErrorStreamEmpty
            return bytes(buffer[:i])
        buffer[i] = thebyte
    error = e.NoError
    return bytes(buffer)