import socket
import random
from .udpserver import *
from .packet import *

from tornado.gen import coroutine, Return, sleep
from tornado.iostream import IOStream


UDT_VER = 4
MAX_PKT_SIZE = 1500

# Socket types
STREAM = 1
DGRAM  = 2
UDP = DGRAM
TCP = STREAM

# IP version
AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6

#
_srandom = random.SystemRandom().random
random = lambda p: int(_srandom()*10**p)

### Base Class

class BaseUDTSocket:

	handshaked = False

	@coroutine
	def _handle_packet(self, client):
		while 1:
			header_size = ControlHeader.size()
			h_data = yield client.get_bytes(header_size)

			if bit_flag_from_byte(h_data[0]):
				# Control packet

				h = ControlHeader(h_data)

				c_handler = self.control_handler.get(h.get_msg_type(),
					lambda *a:1)
				yield c_handler(self, client, h)

			else:
				# Data Packet
				pass

	@coroutine
	def _handle_handshake(self, client, header):
		handshake_size = HandshakePacket.size()

		data = yield client.get_bytes(handshake_size)
		p = HandshakePacket(data, header=header)
		print "!", p

		if p.header.dst_sock_id == 0:
			p.header.dst_sock_id = p.sock_id
			p.syn_cookie = client.syn_cookie
			data = p.pack()
			client.send(data)
			print "> Initiate handshake"

		elif p.req_type > 0:
			p.req_type = -1
			data = p.pack()
			self.send(data)
			self.handshaked = True
			print "> Acknowledge handshake"

		elif p.syn_cookie == client.syn_cookie:
			self.handshaked = True
			print "> Handshake accepted"

	control_handler = {
		ControlPacket.handshake: _handle_handshake
	}



### Client

class UDTSocket(BaseUDTSocket, IOStream):
	def __init__(self, host, port, s_type=DGRAM, ip_version=AF_INET, io_loop=None):
		self.sock_type = s_type
		s_type = socket.SOCK_STREAM if s_type == TCP else socket.SOCK_DGRAM
		s = socket.socket(ip_version, s_type)
		super(UDTSocket, self).__init__(s, io_loop=io_loop)
		self.host = host
		self.port = port

		self.mss = MAX_PKT_SIZE
		self.flight_flag_size = 25600
		self.linger_onoff = 1
		self.linger = 180
		self.ip_version = ip_version
		self.snd_timeout = -1
		self.rcv_timeout = -1
		self.reuse_addr = True
		self.max_bw = -1
		self.udt_ver = UDT_VER
		self.sock_id = random(6)

	def set_reuse_addr(self):
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	@coroutine
	def connect(self):
		if self.reuse_addr:
			self.set_reuse_addr()

		yield super(UDTSocket, self).connect((self.host, self.port))

		# Start packet deserialization loop
		self._handle_packet(self)

		h = yield self.handshake()
		raise Return(h)

	def get_bytes(self, n_bytes):
		return self.read_bytes(n_bytes)

	def send(self, data):
		return self.write(data)

	@coroutine
	def handshake(self):
		p = HandshakePacket(
			req_type=1,
			udt_ver=self.udt_ver,
			sock_type=self.sock_type,
			init_pkt_seq=0,
			max_pkt_size=self.mss,
			max_flow_win_size=self.flight_flag_size,
			sock_id=self.sock_id,
			syn_cookie=0,
			sock_addr=self.socket.getpeername()[0]
		)
		b = p.pack()

		for i in xrange(10):
			self.send(b)
			print "^ Send handshake"

			for u in xrange(12):
				yield sleep(.5)
				if self.handshaked:
					raise Return(True)

		raise Return(False)

### Server

class UDTServer(BaseUDTSocket, UDPServer):

	def on_accept(self, client):
		client.syn_cookie = random(6)
		self._handle_packet(client)

	def on_close(self, client):
		# send shutdown
		pass