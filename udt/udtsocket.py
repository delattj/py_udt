import socket
import random
from .udpclient import *
from .udpserver import *
from .packet import *

from tornado.gen import coroutine, Return, sleep

UDT_VER = 4
MTU = 1500 # default ethernet settings
# Other commun MTU:
	# 1492   IEEE 802.3
	# 1006   SLIP, ARPANET
	# 576    X.25 Networks
	# 544    DEC IP Portal
	# 512    NETBIOS
	# 508    IEEE 802/Source-Rt Bridge, ARCNET
	# 296    Point-to-Point (low delay)
	# 68     Official minimum
### Prevent packet fragmentation
### Linux
# IP_MTU_DISCOVER   = 10
# IP_PMTUDISC_DONT  =  0  # Never send DF frames.
# IP_PMTUDISC_WANT  =  1  # Use per route hints.
# IP_PMTUDISC_DO    =  2  # Always DF.
# IP_PMTUDISC_PROBE =  3  # Ignore dst pmtu.
# s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# s.setsockopt(socket.SOL_IP, IP_MTU_DISCOVER, IP_PMTUDISC_DO)
### Windows
# IP_DONTFRAGMENT   =  9
# s.setsockopt(socket.IPPROTO_IP, IP_DONTFRAGMENT, 1)
### ad-hoc MTU discovery
# ping 192.168.2.38 -l 1472 -f

# UDT socket types
STREAM = 1 # time-to-live and in order msg options
DGRAM  = 2

# IP version
AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6

#
_srandom = random.SystemRandom().random
random = lambda p: int(_srandom()*10**p)

### Base Class

class HandshakeTimeout(Exception):
	pass

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

				c_handler = self.control_handler.get(h.get_msg_type(), None)
				if not c_handler:
					continue

				c_handler(self, client, h, p_data[ctrl_header_size:])

			else:
				# Data Packet
				self._handle_data(client, p_dataata)

	def _handle_data(self, client, data_packed):
		p = DataPacket(data_packed)
		print "@", p.seq

		# client.rcv_data[][] = p.data


	def _handle_handshake(self, client, header, data):
		p = HandshakePacket(data, header=header)
		print "!", p

		if p.header.dst_sock_id == 0:
			p.header.dst_sock_id = p.sock_id
			p.syn_cookie = client.syn_cookie
			client.sock_id = p.sock_id
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

		for i in xrange(20):
			self.write(b)
			print "^ Send handshake"

			for u in xrange(12):
				yield sleep(.25)

				if self.handshaked:
					raise Return(True)

				if self.closed():
					raise Return(False)

		raise HandshakeTimeout()

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