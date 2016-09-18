import socket
import random
from .udpclient import *
from .udpserver import *
from .packet import *

from tornado.gen import coroutine, Return, sleep
from tornado.iostream import IOStream


UDT_VER = 4
MTU = 1500

# Socket types
STREAM = 1
DGRAM  = 2

# IP version
AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6

#
_srandom = random.SystemRandom().random
random = lambda p: int(_srandom()*10**p)

### Base Class

ctrl_header_size = ControlHeader.size()

class BaseUDTSocket:

	handshaked = False

	@coroutine
	def _handle_packet(self, client):
		while 1:
			p_data = yield client.get_next_packet()

			if bit_flag_from_byte(p_data[0]):
				# Control packet

				h = ControlHeader(p_data[:ctrl_header_size])

				c_handler = self.control_handler.get(h.get_msg_type(),
					lambda *a:1)
				yield c_handler(self, client, h, p_data[ctrl_header_size:])

			else:
				# Data Packet
				pass

	@coroutine
	def _handle_handshake(self, client, header, data):
		p = HandshakePacket(data, header=header)
		print "!", p

		if p.header.dst_sock_id == 0:
			p.header.dst_sock_id = p.sock_id
			p.syn_cookie = client.syn_cookie
			data = p.pack()
			client.write(data)
			print "> Initiate handshake"

		elif p.req_type > 0:
			p.req_type = -1
			data = p.pack()
			self.write(data)
			self.handshaked = True
			print "> Acknowledge handshake"

		elif p.syn_cookie == client.syn_cookie:
			self.handshaked = True
			print "> Handshake accepted"

	control_handler = {
		ControlPacket.handshake: _handle_handshake
	}


### Client

class UDTSocket(BaseUDTSocket, UDPSocket):
	def __init__(self, host, port, ip_version=AF_INET, io_loop=None):
		super(UDTSocket, self).__init__(host, port,
			ip_version=ip_version, mtu=MTU,
			io_loop=io_loop
		)

		self.sock_type = DGRAM
		self.ip_version = ip_version
		self.udt_ver = UDT_VER
		self.sock_id = random(6)

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
			self.write(b)
			print "^ Send handshake"

			for u in xrange(12):
				yield sleep(.5)
				if self.handshaked:
					raise Return(True)

		raise Return(False)

	@coroutine
	def connect(self):
		yield super(UDTSocket, self).connect()

		# Start packet deserialization loop
		self._handle_packet(self)

		yield self.handshake()

	def connected(self):
		return super(UDTSocket, self).connected() and self.handshaked

	def on_close(self):
		# send shutdown
		pass


### Server

class UDTServer(BaseUDTSocket, UDPServer):

	def on_accept(self, client):
		client.syn_cookie = random(6)
		self._handle_packet(client)

	def on_close(self, client):
		# send shutdown
		pass