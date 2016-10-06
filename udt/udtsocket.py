import socket
import random
from .udpclient import *
from .udpserver import *
from .packet import *
from .sequence import *

from types import MethodType, FunctionType
from tornado.gen import coroutine, sleep, Return, Future
from tornado.locks import Event

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
_rstruct = Struct('>I')
random_id = lambda: _rstruct.unpack(os.urandom(4))[0]

def inlay(target, source):
	'''Hot patch *target* instance with methods from *source* class'''
	for method_name, method in source.__dict__.items():
		if isinstance(method, FunctionType):
			b_method = MethodType(method, target, target.__class__)
			setattr(target, method_name, b_method)

class EventQueue(object):
	__slots__ = ('_queue',)

	def __init__(self):
		self._queue = deque()

	def next(self, n=None):
		q = self._queue 
		if q:
			if n is None or n == 1:
				q.popleft().set_result(None)

			elif n > 0:
				for _ in xrange(min(n, len(q))):
					q.popleft().set_result(None)

	def all(self):
		q = self._queue 
		if q:
			for _ in xrange(len(q)):
				q.popleft().set_result(None)

	def wait(self):
		f = Future()
		self._queue.append(f)
		return f

	def __nonzero__(self):
		return bool(self._queue)

### Base Class

seq_keeper = SequenceKeeper(0x7FFFFFFF)
ctrl_header_size = ControlHeader.size()
data_header_size = DataPacket.size()

class HandshakeTimeout(Exception):
	pass

class BaseUDTSocket:

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

			elif client.handshaked:
				# Data Packet
				self._handle_data(client, p_data)

	def _handle_data(self, client, data_packed):
		p = DataPacket(data_packed)
		client.push_data(p.seq, p.data)

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
			client.handshaked = True
			print "> Acknowledge handshake"

		elif p.syn_cookie == client.syn_cookie:
			client.handshaked = True
			print "> Handshake accepted"

	control_handler = {
		ControlPacket.handshake: _handle_handshake
	}

class DataQueue(object):

	def initialize(self, window_size=25600, write_queue=None):
		self._rcv_data = DictSequence(window_size, seq_keeper)
		self._sent_data = DictSequence(window_size, seq_keeper)
		self._left_over = ""
		self._data_event = Event()
		self._write_queue = EventQueue() if write_queue is None else write_queue
		self._next_seq = -1

	def push_data(self, seq, data):
		# print "@", seq
		last_no = self._rcv_data.seq_no

		offset = seq_keeper.offset(last_no, seq)
		if offset < 1:
			return # drop that packet, we already received it.

		self._rcv_data[seq] = data

		# data loss detection
		next_seq = self._rcv_data.next_seq()
		offset = seq_keeper.offset(seq, next_seq)
		if offset < 0:
			print "@ data lost", seq_keeper.incr(next_seq)

		# Notify if we have a sequense of data that can be read
		if self._rcv_data.has_seq_data():
			self._data_event.set()

	@coroutine
	def recv(self, max_len):
		yield self._data_event.wait()
		if self.closed():
			raise Shutdown()

		data = self._left_over
		if data:
			max_len -= len(data)

		for d in self._rcv_data:
			data += d
			max_len -= len(d)
			if max_len <= 0:
				break

		if max_len < 0:
			self._left_over = data[max_len:]
			data = data[:max_len]

		else:
			self._left_over = ""
			if not self._rcv_data.has_seq_data():
				self._data_event.clear()

		raise Return(data)

	@coroutine
	def recv_stream(self):
		yield self._data_event.wait()
		if self.closed():
			raise Shutdown()

		self._data_event.clear()
		raise Return(''.join(self._rcv_data))

	@coroutine
	def recv_file(self, fd, length):
		while length:
			# print ">", length
			yield self._data_event.wait()
			if self.closed():
				raise Shutdown()

			for d in self._rcv_data:
				length -= len(d)
				fd.write(d)
				if length == 0:
					break

			if not self._rcv_data.has_seq_data():
				self._data_event.clear()

	@coroutine
	def send(self, data):
		if self._write_queue:
			yield self._write_queue.wait()
			if self.closed():
				raise Shutdown()

		q = 1
		length = len(data)
		data_size = self.mss - data_header_size
		n_packet = length / data_size + int(bool(length % data_size))
		for n in xrange(n_packet):
			p = DataPacket(
				sock_id=self.sock_id,
				data=data[n*data_size:(n+1)*data_size]
			)
			p.set_seq(self._sent_data.add(p))

			pack = p.pack()
			write_future = self.write(pack)
			if write_future is not None:
				if not self._write_queue:
					self._write_queue.wait()
					q += 1

				yield write_future
				self.write(pack)

		self._write_queue.next(q)

	@coroutine
	def send_file(self, fd, length):
		if self._write_queue:
			yield self._write_queue.wait()
			if self.closed():
				raise Shutdown()

		q = 1
		data_size = self.mss - data_header_size
		n_packet = length / data_size + int(bool(length % data_size))
		for n in xrange(n_packet):
			p = DataPacket(
				sock_id=self.sock_id,
				data=fd.read(data_size)
			)
			assert len(p.data) > 0, "Data packet is empty!"
			p.set_seq(self._sent_data.add(p))
			# print "%", p.seq, len(p.data)
			del self._sent_data[p.seq] # until ack is intruduced, else it leaks

			pack = p.pack()
			write_future = self.write(pack)
			if write_future is not None:
				if not self._write_queue:
					self._write_queue.wait()
					q += 1

				# print "@@@@@@@@"
				# yield sleep(.001)

				yield write_future
				self.write(pack)

		self._write_queue.next(q)


### Client

class UDTSocket(DataQueue, BaseUDTSocket, UDPSocket):
	def __init__(self, host, port, ip_version=AF_INET, io_loop=None,
		mtu=MTU, window_size=25600):

		super(UDTSocket, self).__init__(host, port,
			ip_version, io_loop, mtu, window_size
		)
		self.initialize(window_size)

		self.handshaked = False
		self.sock_type = DGRAM
		self.ip_version = ip_version
		self.udt_ver = UDT_VER
		self.sock_id = random_id()

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
		self._data_event.set()

### Server

class UDTServer(BaseUDTSocket, UDPServer):

	def __init__(self, ip_version=AF_INET, io_loop=None,
		mtu=1500, window_size=25600):

		super(UDTServer, self).__init__(ip_version, io_loop, mtu, window_size)

		self._write_queue = EventQueue()

	def on_accept(self, client):
		client.syn_cookie = random_id()
		client.mss = self.mss
		client.handshaked = False

		inlay(client, DataQueue)
		client.initialize(self.flight_flag_size, self._write_queue)

		self._handle_packet(client)
		self._data_stream(client)

	def on_close(self, client):
		# send shutdown
		client._data_event.set()

	@coroutine
	def _data_stream(self, client):
		while 1:
			yield client._data_event.wait()
			yield self.on_data_ready(client)

	@coroutine
	def on_data_ready(self, client):
		'''Server connection on data callback'''

		raise NotImplemented