import socket
from collections import deque

from .udpclient import *
from .udpclient import _ERRNO_WOULDBLOCK

from tornado.ioloop import IOLoop
from tornado.gen import coroutine, Return, Future

class UDPClient(object):
	def __init__(self, server, addr, flight_flag_size):
		self.addr = addr
		self._inbound_packet = deque(maxlen=flight_flag_size)
		self.flight_flag_size = flight_flag_size
		self.shutdown = False
		self._server = server
		self._writeto = server._writeto

		self._waiting_packet = None

	def write(self, data):
		self._writeto(data, self.addr)

	def has_packet(self):
		return bool(self._inbound_packet)

	def push_packet(self, packet):
		if len(self._inbound_packet) >= self.flight_flag_size:
			return # drop packet

		self._inbound_packet.append(packet)

	@coroutine
	def get_next_packet(self):
		assert self._waiting_packet is None

		if not self._inbound_packet:
			f = Future()
			self._waiting_packet = f
			r = yield f
			if not r:
				raise Shutdown()

		b = self._inbound_packet.popleft()

		raise Return(b)

	def _wake_get_next_packet(self):
		if self._waiting_packet is None:
			return

		if not self._inbound_packet:
			return

		self._waiting_packet.set_result(1)
		self._waiting_packet = None

	def _shutdown_get_next_packet(self):
		if self._waiting_packet is None:
			return

		self._waiting_packet.set_result(0)
		self._waiting_packet = None

	def closed(self):
		return self.shutdown

	def close(self):
		self._server.on_close(self)
		self._shutdown_get_next_packet()
		del self._server.clients[self.addr]
		self.shutdown = True

class UDPServer(object):
	def __init__(self, ip_version=AF_INET, io_loop=None,
		mtu=1500, window_size=25600):

		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self._state = None
		self.io_loop = io_loop or IOLoop.instance()
		self.port = None
		self.clients = {}
		self._outbound_packet = deque(maxlen=window_size)
		self.flight_flag_size = window_size
		self.mss = mtu - 28 # 28 -> IP header size

	def bind(self, port):
		self.port = port
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.socket.setblocking(0)
		self.socket.bind(('', port))
		self._add_io_state(self.io_loop.READ)

	def start(self):
		IOLoop.instance().start()

	def _add_io_state(self, state):
		if self._state is None:
			self._state = IOLoop.ERROR | state
			self.io_loop.add_handler(
				self.socket.fileno(), self._handle_events, self._state
			)

		elif not self._state & state:
			self._state = self._state | state
			self.io_loop.update_handler(self.socket.fileno(), self._state)

	def _remove_io_state(self, state):
		if self._state is not None and self._state & state:
			self._state ^= state
			self.io_loop.update_handler(self.socket.fileno(), self._state)

	def closed(self):
		return self.socket is None

	def close(self):
		for c in self.clients.values():
			c.close()
		self.io_loop.remove_handler(self.socket.fileno())
		self.socket.shutdown(socket.SHUT_RDWR)
		self.socket.close()
		self.socket = None

	def _get_client(self, addr):
		if addr in self.clients:
			c = self.clients[addr]

		else:
			c = UDPClient(self, addr, self.flight_flag_size)
			self.clients[addr] = c
			self.io_loop.spawn_callback(self.on_accept, c)

		return c

	def _handle_read(self):
		clients = set() # keep track of delivered clients

		try:
			while 1:

				b, addr = self.socket.recvfrom(self.mss)

				if not b:
					continue

				c = self._get_client(addr)
				clients.add(c)
				c.push_packet(b)

		except socket.error as e:
			if e.args[0] not in _ERRNO_WOULDBLOCK:
				self.close()
				raise

		for c in clients:
			# Wake up client socket
			c._wake_get_next_packet()

	def _writeto(self, data, addr):
		self._outbound_packet.append((data, addr))
		self._add_io_state(self.io_loop.WRITE)

	def _handle_write(self):
		outbound = self._outbound_packet
		try:
			while outbound:
				b, addr = outbound[0]
				self.socket.sendto(b, addr)
				outbound.popleft() # remove only if it worked

			self._remove_io_state(self.io_loop.WRITE)

		except socket.error as e:
			if e.args[0] in _ERRNO_WOULDBLOCK:
				return # retry later

			self._get_client(addr).close()
			raise

	def _handle_events(self, fd, events):
		if self.closed():
			return

		if events & self.io_loop.READ:
			self._handle_read()

		if events & self.io_loop.WRITE:
			self._handle_write()

		if events & self.io_loop.ERROR:
			print ('ERROR Event in %s' % self)

	def on_accept(self, client):
		'''On accept new client connection'''

		raise NotImplemented

	def on_close(self, client):
		'''Shutdown connection to client'''

		raise NotImplemented
