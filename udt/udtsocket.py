import socket
from .packet import *
from .buffer import *

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

class UDTSocket(object):
	def __init__(self, host, port, s_type=DGRAM, ip_version=AF_INET):
		self.sock_type = s_type
		s_type = socket.SOCK_STREAM if s_type == TCP else socket.SOCK_DGRAM
		self._socket = socket.socket(ip_version, s_type)
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

	def set_reuse_addr(self):
		self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	def connect(self):
		if self.reuse_addr:
			self.set_reuse_addr()

		self._socket.connect((self.host, self.port))

	def listen(self):
		if self.reuse_addr:
			self.set_reuse_addr()

		self._socket.bind((self.host, self.port))

	def _send(self, data):
		return self._socket.sendall(data)

	def _recv(self, size):
		return self._socket.recv(size)

	def _recv_into(self, bufferio, size):
		return self._socket.recv_into(bufferio, size)

	def close(self):
		self._socket.close()

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
			sock_addr=self._socket.getpeername()[0]
		)
		b = BytesIO(self.mss)
		p.pack_into(b)
		self._send(b.read())

		self._recv_into(b, p.size())
		p.unpack_from(b)
		p.header.dst_sock_id = p.sock_id
		p.req_type = -1
		p.pack_into(b)
		self._send(b.read())

# def server():
# 	import socket

# 	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 	s.bind(('', 47008))
# 	while 1:
# 		(d, addr) = s.recvfrom(1024)
# 		if not d: break
# 		print "Recieved from "+ str(addr)
# 		print "###", len(d)
# 	s.close()
