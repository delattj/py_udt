from struct import Struct

# Leading bit for control data packets
flag_bit_32 = 1 << 31 # 32 bit
flag_bit_16 = 1 << 15 # 16 bit

# Control packet types
handshake    = 0x0
keepalive    = 0x1
ack          = 0x2
nak          = 0x3
congestion   = 0x4 # Congestion Warning
shutdown     = 0x5
ack2         = 0x6
msg_drop_req = 0x7

class Packet(object):
	__slots__ = (
		'ts',
		'dst_sock_id',
	)
	_struct = Struct('>II')

	def __init__(self, **kwargs):
		for attr in self.__slots__:
			setattr(self, attr, kwargs.get(attr, 0))

	def pack_into(self, bufferio):
		self._struct.pack_into(bufferio, bufferio.tell(),
			self.ts,
			self.dst_sock_id
		)
		bufferio.seek(bufferio.tell() + self._struct.size)

	def unpack_from(self, bufferio):
		self.ts, self.dst_sock_id = self._struct.unpack_from(bufferio)

	def __repr__(self):
		r = self.__class__.__name__ +'('
		r += ', '.join(
			attr +'='+ repr(getattr(self, attr)) for attr in self.__slots__
		)
		return r +')'

	def size(self):
		if hasattr(self, 'header'):
			return self.header._struct.size + self._struct.size
		return self._struct.size

class DataPacket(Packet):
	__slots__ = (
		'seq',
		'msg',
		'ts',
		'dst_sock_id',
		'data',
	)
	_struct = Struct('>IIII')

	def __init__(self, **kwargs):
		super(DataPacket, self).__init__(**kwargs)
		if not self.data:
			self.data = b''

	def set_seq(self, seq):
		self.seq = seq & 0x7FFFFFFF

	def set_msg(self, boundary, order, msg):
		self.msg = (boundary << 30) | (order << 29) | (msg & 0x1FFFFFFF)

	def get_msg_boundary(self):
		return self.msg >> 30

	def get_msg_order_flag(self):
		return (1 == ((self.msg >> 29) & 1))

	def get_msg(self):
		return self.msg & 0x1FFFFFFF

	def pack_into(self, bufferio):
		self._struct.pack_into(bufferio, 0,
			*[getattr(self, a) for a in self.__slots__[:-1]]
		)
		bufferio.write(self.data, self._struct.size)

	def unpack_from(self, bufferio, size):
		struct = self._struct
		unpacked = struct.unpack_from(bufferio)
		for attr, value in zip(self.__slots__[:-1], unpacked):
			setattr(self, attr, value)
		self.data = bufferio.read(size, struct.size)

class ControlHeader(Packet):
	__slots__ = (
		'msg_type',
		'unused',
		'info',
		'ts',
		'dst_sock_id',
	)
	_struct = Struct('>HHIII')

	def __init__(self, **kwargs):
		super(ControlHeader, self).__init__(**kwargs)
		self.set_msg_type(self.msg_type)

	def set_msg_type(self, msg_type):
		self.msg_type = (msg_type & 0x7fff) | flag_bit_16

	def get_msg_type(self):
		return self.msg_type & 0x7fff

	def pack_into(self, bufferio):
		self._struct.pack_into(bufferio, 0,
			self.msg_type,
			0,
			self.info,
			self.ts,
			self.dst_sock_id
		)
		bufferio.seek(self._struct.size)

	def unpack_from(self, bufferio):
		unpacked = self._struct.unpack_from(bufferio)
		for attr, value in zip(self.__slots__, unpacked):
			setattr(self, attr, value)

class HandshakePacket(Packet):
	__slots__ = (
		'header',
		'udt_ver',           # UDT version
		'sock_type',         # Socket Type (1 = STREAM or 2 = DGRAM)
		'init_pkt_seq',      # initial packet sequence number
		'max_pkt_size',      # maximum packet size (including UDP/IP headers)
		'max_flow_win_size', # maximum flow window size
		'req_type',          # connection type (regular(1), rendezvous(0), -1/-2 response)
		'sock_id',           # socket ID
		'syn_cookie',        # SYN cookie
		'sock_addr',         # the IP address of the UDP socket to which this packet is being sent
	)
	_struct = Struct('>IIIIIiII16s')

	def __init__(self, **kwargs):
		kwargs['msg_type'] = handshake
		super(HandshakePacket, self).__init__(**kwargs)
		if not self.sock_addr:
			self.sock_addr = b''
		if not self.header:
			self.header = ControlHeader(**kwargs)

	def pack_into(self, bufferio):
		self.header.pack_into(bufferio)
		self._struct.pack_into(bufferio, bufferio.tell(),
			*[getattr(self, a) for a in self.__slots__[1:]]
		)
		bufferio.seek(bufferio.tell() + self._struct.size)

	def unpack_from(self, bufferio):
		self.header.unpack_from(bufferio)
		unpacked = self._struct.unpack_from(bufferio, self.header._struct.size)
		for attr, value in zip(self.__slots__[1:], unpacked):
			setattr(self, attr, value)
		t = self.sock_addr.find('\0')
		if t >= 0:
			self.sock_addr = self.sock_addr[:t]

