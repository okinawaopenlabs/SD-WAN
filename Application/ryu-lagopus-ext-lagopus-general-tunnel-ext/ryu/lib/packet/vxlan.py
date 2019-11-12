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


class vxlan(packet_base.PacketBase):
    """
    """

    _PACK_STR = '!BxxxI'
    _MIN_LEN = struct.calcsize(_PACK_STR)

    def __init__(self, flags=0x8, vni=0):
        super(vxlan, self).__init__()
        self.flags = flags
        self.vni = vni

    @classmethod
    def parser(cls, buf):
        (flags, vni) = struct.unpack_from(cls._PACK_STR, buf)
        vni = vni >> 8
        msg = cls(flags, vni)
        return msg, vxlan.get_packet_type(0), buf[msg._MIN_LEN:]

    def serialize(self, payload, prev):
        return struct.pack(vxlan._PACK_STR, self.flags, self.vni << 8)
