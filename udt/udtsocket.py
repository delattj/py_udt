import socket
from .udpserver import *
from .packet import *
from .buffer import *

from tornado.gen import coroutine, Return
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

### Client

class UDTSocket(IOStream):
	def __init__(self, host, port, s_type=DGRAM, ip_version=AF_INET, io_loop=None):
		self.sock_type = s_type
		s_type = socket.SOCK_STREAM if s_type == TCP else socket.SOCK_DGRAM
		s = socket.socket(ip_version, s_type)
		super(UDTSocket, self).__init__(s, io_loop=io_loop)
		self.host = host
		self.port = port

		self.mss = MAX_PKT_SIZE
		self.sync_sending = True
		self.sync_recving = True
		self.flight_flag_size = 25600
		self.snd_buff_size = 8192
		self.rcv_buff_size = 8192 #rcv buffer MUST NOT be bigger than Flight Flag size
		self.linger_onoff = 1
		self.linger = 180
		self.udp_snd_buff_size = 65536
		self.udp_rcv_buff_size = self.rcv_buff_size * self.mss
		self.ip_version = ip_version
		self.rendezvous = False
		self.snd_timeout = -1
		self.rcv_timeout = -1
		self.reuse_addr = True
		self.max_bw = -1

		self.udt_ver = UDT_VER

		self.handshaked = False

	def set_reuse_addr(self):
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	@coroutine
	def connect(self):
		if self.reuse_addr:
			self.set_reuse_addr()

		yield super(UDTSocket, self).connect((self.host, self.port))

		h = yield self.handshake()
		raise Return(h)

	@coroutine
	def get_bytes(self, n_bytes):
		data = yield self.read_bytes(n_bytes)
		b = BytesIO(len(data))
		b.write(data)
		raise Return(b)

	def send(self, bufferio):
		return super(UDTSocket, self).write(str(bufferio))

	@coroutine
	def handshake(self):
		p = HandshakePacket(
			req_type=1,
			udt_ver=self.udt_ver,
			sock_type=self.sock_type,
			init_pkt_seq=0, # rand value?
			max_pkt_size=self.mss,
			max_flow_win_size=self.flight_flag_size,
			sock_id=1, # rand value?
			syn_cookie=0,
			sock_addr=self.socket.getpeername()[0]
		)
		b = p.pack()
		self.send(b)

		b = yield self.get_bytes(ControlHeader.size())
		if not bit_flag_from_byte(b[0]):
			raise Return(False)

		h = ControlHeader(b)
		if h.get_msg_type() != ControlPacket.handshake:
			raise Return(False)

		b = yield self.get_bytes(HandshakePacket.size())
		p = HandshakePacket(b, header=h)
		print "@ %s"% p
		if p.req_type == 1:
			print "^ Handshake response"
			# print "$", p.header.dst_sock_id
			# p.header.dst_sock_id = p.sock_id
			p.req_type = -1
			b = p.pack()
			self.send(b)
			self.handshaked = True

		raise Return(self.handshaked)


### Server

class UDTServer(UDPServer):

	@coroutine
	def accept(self, client):
		while 1:
			header_size = ControlHeader.size()
			h_buff = yield client.get_bytes(header_size)

			if bit_flag_from_byte(h_buff[0]):
				# Control packet

				h = ControlHeader(h_buff)

				c_handler = self.control_handler.get(h.get_msg_type(),
					lambda *a:1)
				yield c_handler(self, client, h)

			else:
				# Data Packet
				pass

	@coroutine
	def handle_handshake(self, client, header):
		handshake_size = HandshakePacket.size()

		hd_buff = yield client.get_bytes(handshake_size)
		p = HandshakePacket(hd_buff, header=header)
		print "!", p

		if p.header.dst_sock_id == 0:
			p.header.dst_sock_id = p.sock_id
			p.syn_cookie = 111 # client.syn_cookie
			bufferio = p.pack()
			client.send(bufferio)

		elif p.req_type > 0:
			print "> Acknowledge handshake"

		elif p.syn_cookie == 111: # client.syn_cookie
			self.handshake = True
			print "> Handshake accepted"

	control_handler = {
		ControlPacket.handshake: handle_handshake
	}

	def shutdown(self, client):
		# send shutdown
		pass