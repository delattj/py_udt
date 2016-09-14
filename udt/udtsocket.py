import socket
from .udpserver import *
from .packet import *
from .buffer import *

from tornado.gen import coroutine, Return, Future
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

	def connect(self):
		if self.reuse_addr:
			self.set_reuse_addr()

		f = Future()
		def on_connect(f_c):
			if f_c.exception():
				f.set_exc_info(f_c._exc_info)
				return

			h_future = self.handshake()
			def on_handshake(f_h):
				if f_h.exception():
					f.set_exc_info(f_h._exc_info)
					return
				f.set_result(f_h.result())

			self.io_loop.add_future(h_future, on_handshake)

		f_connect = super(UDTSocket, self).connect((self.host, self.port))
		self.io_loop.add_future(f_connect, on_connect)
			
		return f

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
		self.write(str(b.read()))
		b.set_length(0)

		data = yield self.read_bytes(ControlHeader.size())
		b.write(data)
		p = HandshakePacket(b)
		print "@ %s"% p
		if p.req_type == 1:
			print "^ Handshake response"
			# print "$", p.header.dst_sock_id
			# p.header.dst_sock_id = p.sock_id
			p.req_type = -1
			p.pack_into(b)
			self.write(str(b.read()))
			self.handshaked = True

		raise Return(self.handshaked)


### Server

def _retry_onfail(handler):
	def _fnc(s, client, *args):
		if not handler(s, client, *args):
			client._packet_handler = (handler, args)
			return 0

		client._packet_handler = None
		return 1

	return _fnc

class UDTServer(UDPServer):

	def handle_packet(self, client):
		if hasattr(client, '_packet_handler')\
				and client._packet_handler is not None:
			# resume after running out of bytes
			handler, args = client._packet_handler
			if not handler(self, client, *args):
				return

		while 1:
			header_size = ControlHeader.size()
			h_buff = client.get_bytes(header_size)
			if h_buff is None:
				break # Not enough bytes to shew

			if bit_flag_from_byte(h_buff[0]):
				# Control packet

				h = ControlHeader(h_buff)

				c_handler = self.control_handler.get(h.get_msg_type(),
					lambda *a:1)
				if not c_handler(self, client, h):
					break

			else:
				# Data Packet
				pass

	@_retry_onfail
	def handle_handshake(self, client, header):
		handshake_size = HandshakePacket.size()

		hd_buff = client.get_bytes(handshake_size)
		if hd_buff:
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

			return 1

	control_handler = {
		ControlPacket.handshake: handle_handshake
	}

