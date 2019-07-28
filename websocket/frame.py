def is_bytes(arg):
    return isinstance(arg, bytes) or isinstance(arg, bytearray) or isinstance(arg, memoryview)

class WebsocketFrame:
    def __init__(self):
        self._m_field_flags_opcode = None
        self._m_field_mask_len = None
        self._m_field_len2 = None
        self._m_field_len6 = None
        self._m_field_maskkey = None
        self._payload_buffer = None
        self._payload_bytesrecved = 0

    @property
    def _field_flags_opcode(self):
        return self._m_field_flags_opcode
    @_field_flags_opcode.setter
    def _field_flags_opcode(self, value):
        if value is None:
            self._m_field_flags_opcode = None
        elif is_bytes(value):
            self._m_field_flags_opcode = int.from_bytes(value, 'big')
        else:
            raise ValueError("field must be a bytes-like object")
    @property
    def _field_mask_len(self):
        return self._m_field_mask_len
    @_field_mask_len.setter
    def _field_flags_opcode(self, value):
        if value is None:
            self._m_field_flags_opcode = None
        elif is_bytes(value):
            self._m_field_flags_opcode = int.from_bytes(value, 'big')
        else:
            raise ValueError("field must be a bytes-like object")
    @property
    def _field_len2(self):
        return self._m_field_len2
    @_field_len2.setter
    def _field_flags_opcode(self, value):
        if value is None:
            self._m_field_flags_opcode = None
        elif is_bytes(value):
            self._m_field_flags_opcode = int.from_bytes(value, 'big')
        else:
            raise ValueError("field must be a bytes-like object")
    @property
    def _field_len6(self):
        return self._m_field_len6
    @_field_len6.setter
    def _field_flags_opcode(self, value):
        if value is None:
            self._m_field_flags_opcode = None
        elif is_bytes(value):
            self._m_field_flags_opcode = int.from_bytes(value, 'big')
        else:
            raise ValueError("field must be a bytes-like object")
    @property
    def _field_maskkey(self):
        return self._m_field_maskkey
    @_field_maskkey.setter
    def _field_flags_opcode(self, value):
        if value is None:
            self._m_field_flags_opcode = None
        elif is_bytes(value):
            self._m_field_flags_opcode = int.from_bytes(value, 'big')
        else:
            raise ValueError("field must be a bytes-like object")

    @property
    def flag_fin(self):
        if self._field_flags_opcode is None:
            return None
        return bool(self._field_flags_opcode & 0x80)
    @property
    def flag_rsv1(self):
        if self._field_flags_opcode is None:
            return None
        return bool(self._field_flags_opcode & 0x40)
    @property
    def flag_rsv2(self):
        if self._field_flags_opcode is None:
            return None
        return bool(self._field_flags_opcode & 0x20)
    @property
    def flag_rsv3(self):
        if self._field_flags_opcode is None:
            return None
        return bool(self._field_flags_opcode & 0x10)
    @property
    def opcode(self):
        if self._field_flags_opcode is None:
            return None
        return int(self._field_flags_opcode & 0x0f)
    @property
    def flag_mask(self):
        if self._field_mask_len is None:
            return None
        return bool(self._field_mask_len & 0x80)
    @property
    def payload_length(self):
        if self._field_mask_len is None:
            return None
        length = int(self._field_mask_len & 0x7f)
        if length < 126:
            return length
        if self._field_len2 is None:
            return None
        length2 = int(self._field_len2)
        if length == 126:
            return length2
        if self._field_len6 is None:
            return None
        length6 = int(self._field_len6)
        if length == 127:
            return (length2 << (6*8)) + length6
        return None
    @property
    def maskkey(self):
        if self._field_maskkey is None:
            return None
        return int(self._field_maskkey)
        