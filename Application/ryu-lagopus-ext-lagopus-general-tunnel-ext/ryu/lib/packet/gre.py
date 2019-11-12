# Copyright (C) 2016 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import struct
from . import packet_base
from . import packet_utils


class gre(packet_base.PacketBase):
    """
    """

    _PACK_STR = '!HHI'
    _MIN_LEN = struct.calcsize(_PACK_STR)

    def __init__(self, flags=0x2000, protocol=0, key=0):
        super(gre, self).__init__()
        self.flags = flags
        self.protocol = protocol
        self.key = key

    @classmethod
    def parser(cls, buf):
        (flags, protocol, key) = struct.unpack_from(cls._PACK_STR, buf)
        msg = cls(flags, protocol, key)
        return msg, gre.get_packet_type(protocol), buf[msg._MIN_LEN:]

    def serialize(self, payload, prev):
        hdr = bytearray(struct.pack(gre._PACK_STR, self.flags,
                                    self.protocol, self.key))
        return hdr

    @classmethod
    def get_packet_type(self, protocol):
        return gre._TYPES.get(protocol)
