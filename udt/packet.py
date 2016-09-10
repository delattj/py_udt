from struct import Struct
from .buffer import BytesIO

# Leading bit for control data packets
flag_bit_32 = 1 << 31 # 32 bit
flag_bit_16 = 1 << 15 # 16 bit
bit_flag_from_byte = lambda c: c >> 7

class Packet(object):
	__slots__ = ()
	_struct = Struct('')

	def __init__(self, bufferio=None, **kwargs):
		if bufferio is None:
			for attr in self.__slots__:
				setattr(self, attr, kwargs.get(attr, 0))

		else:
			self.unpack_from(bufferio)

	def fields(self):
		return self.__slots__

	def pack_into(self, bufferio, offset=0):
		self._struct.pack_into(bufferio, offset,
			*[getattr(self, a) for a in self.fields()]
		)
		bufferio.set_length(offset + self.size())

	def pack(self, header_size=0):
		b = BytesIO(header_size+self.size())
		self.pack_into(b)
		return b

	def unpack_from(self, bufferio):
		unpacked = self._struct.unpack_from(bufferio)
		for attr, value in zip(self.fields(), unpacked):
			setattr(self, attr, value)

	def __repr__(self):
		r = self.__class__.__name__ +'('
		r += ', '.join(
			attr +'='+ repr(getattr(self, attr)) for attr in self.__slots__
		)
		return r +')'

	@classmethod
	def size(cls):
		return cls._struct.size

class DataPacket(Packet):
	__slots__ = (
		'seq',
		'msg',
		'ts',
		'dst_sock_id',
		'data',
	)
	_struct = Struct('>IIII')

	def __init__(self, bufferio=None, **kwargs):
		super(DataPacket, self).__init__(bufferio, **kwargs)
		if not self.data:
			self.data = b''

	def fields(self):
		return self.__slots__[:-1]

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
		super(DataPacket, self).pack_into(bufferio)
		bufferio.write(self.data)

	def unpack_from(self, bufferio, data_size=None):
		super(DataPacket, self).unpack_from(bufferio)
		self.data = bufferio.read(data_size, self.size())

class ControlHeader(Packet):
	__slots__ = (
		'msg_type',
		'unused',
		'info',
		'ts',
		'dst_sock_id',
	)
	_struct = Struct('>HHIII')

	def __init__(self, bufferio=None, **kwargs):
		super(ControlHeader, self).__init__(bufferio, **kwargs)
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
		bufferio.set_length(self.size())

class ControlPacket(Packet):
	__slots__ = (
		'header',
	)
	_msg_type = 0

	def __init__(self, bufferio=None, **kwargs):
		if bufferio is None:
			super(ControlPacket, self).__init__(**kwargs)
			if not self.header:
				self.header = ControlHeader(msg_type=self._msg_type, **kwargs)

		else:
			include_header = 'header' in kwargs
			self.unpack_from(bufferio, not(include_header))
			if include_header:
				self.header = kwargs['header']

	def fields(self):
		return self.__slots__[1:]

	def pack_into(self, bufferio):
		self.header.pack_into(bufferio)
		super(ControlPacket, self).pack_into(bufferio, self.header.size())

	def pack(self):
		return super(ControlPacket, self).pack(self.header.size())

	def unpack_from(self, bufferio, with_header=False):
		if with_header:
			self.header = ControlHeader(bufferio)
			bufferio = bufferio[self.header.size():]

		super(ControlPacket, self).unpack_from(bufferio)

	# Control packet types
	handshake    = 0x0
	keepalive    = 0x1
	ack          = 0x2
	nak          = 0x3
	congestion   = 0x4 # Congestion Warning
	shutdown     = 0x5
	ack2         = 0x6
	msg_drop_req = 0x7

class HandshakePacket(ControlPacket):
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
	_msg_type = ControlPacket.handshake

	def __init__(self, bufferio=None, **kwargs):
		super(HandshakePacket, self).__init__(bufferio, **kwargs)
		if not self.sock_addr:
				self.sock_addr = b''

	def unpack_from(self, bufferio, with_header=False):
		super(HandshakePacket, self).unpack_from(bufferio, with_header)
		t = self.sock_addr.find('\0')
		if t >= 0:
			self.sock_addr = self.sock_addr[:t]

