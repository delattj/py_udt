import errno
import socket
from .udpserver import *
from .packet import *
from .buffer import *

from tornado.gen import coroutine, Return, TracebackFuture
from tornado.iostream import IOStream, _ERRNO_WOULDBLOCK


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

### Base Class

class BaseUDTSocket:

	handshaked = False

	@coroutine
	def _handle_packet(self, client):
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
	def _handle_handshake(self, client, header):
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
			self.handshaked = True
			print "> Handshake accepted"

	control_handler = {
		ControlPacket.handshake: _handle_handshake
	}



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
		b = yield self.read_bytes(n_bytes)
		raise Return(b)

	# Override IOStream method to support BytesIO
	def read_from_fd(self):
		b = BytesIO(self.mss)
		n = 0
		try:
			n = self.socket.recv_into(b, self.mss)
			b.set_length(n)

		except socket.error as e:
			if e.args[0] in _ERRNO_WOULDBLOCK:
				return None
			else:
				raise

		if not n:
			self.close()
			return None

		return b.read()

	# Override IOStream method to support BytesIO
	def write(self, bufferio):
		self._check_closed()
		if bufferio:
			self._write_buffer.append(bufferio)
			self._write_buffer_size += len(bufferio)
		future = self._write_future = TracebackFuture()
		future.add_done_callback(lambda f: f.exception())
		if not self._connecting:
			self._handle_write()
			if self._write_buffer:
				self._add_io_state(self.io_loop.WRITE)
			self._maybe_add_error_listener()
		return future
	send = write

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

# Hot patching tornado.iostream
def _merge_prefix(deque, size):
	if len(deque) == 1 and len(deque[0]) <= size:
		return

	prefix = []
	remaining = size

	while deque and remaining > 0:
		chunk = deque.popleft()
		if len(chunk) > remaining:
			deque.appendleft(chunk[remaining:])
			chunk = chunk[:remaining]

		prefix.append(chunk)
		remaining -= len(chunk)

	if prefix:
		b = prefix[0]
		if len(prefix) > 1:
			for x in prefix[1:]:
				b.extend(x)

		deque.appendleft(b)

import tornado.iostream
tornado.iostream._merge_prefix = _merge_prefix

### Server

class UDTServer(BaseUDTSocket, UDPServer):

	def on_accept(self, client):
		self._handle_packet(client)

	def on_close(self, client):
		# send shutdown
		pass