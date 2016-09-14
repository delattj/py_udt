import errno
import socket
from collections import deque

from tornado.ioloop import IOLoop

from .buffer import BytesIO

# IP version
AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6

_ERRNO_WOULDBLOCK = (errno.EWOULDBLOCK, errno.EAGAIN)
if hasattr(errno, "WSAEWOULDBLOCK"):
    _ERRNO_WOULDBLOCK += (errno.WSAEWOULDBLOCK,)

class UDPClient(object):
	def __init__(self, server, addr, window_size):
		self.addr = addr
		self._inbound_packet = deque(maxlen=window_size)
		self.inbound_bytes = 0
		self.handshaked = False
		self._server = server
		self._sendto = server._send

	def send(self, bufferio):
		self._sendto(bufferio, self.addr)

	def has_bytes(self):
		return self.inbound_bytes > 0

	def push_bytes(self, b_bytes):
		self._inbound_packet.append(b_bytes)
		self.inbound_bytes += len(b_bytes)

	def get_bytes(self, n):
		if n and self.inbound_bytes >= n:
			self.inbound_bytes -= n
			bufferio = BytesIO(n)

			while n:
				b = self._inbound_packet[0]
				b_length = len(b)
				acquired = min(b_length, n)
				bufferio.write(b[:acquired])

				if n >= b_length:
					self._inbound_packet.popleft()

				else:
					b[:] = b[n:]

				n -= acquired

			return bufferio

	def close(self):
		self._server.shutdown(self)
		del self._server[self.addr]

class UDPServer(object):
	def __init__(self, ip_version=AF_INET, io_loop=None,
		max_pkt_size=1500, window_size=25600):

		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self._state = None
		self.io_loop = io_loop or IOLoop.instance()
		self.port = None
		self.clients = {}
		self._outbound_packet = deque(maxlen=window_size)
		self.window_size = window_size
		self.max_pkt_size = max_pkt_size

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
		self.io_loop.remove_handler(self.socket.fileno())
		self.socket.shutdown(socket.SHUT_RDWR)
		self.socket.close()
		self.socket = None

	def _get_client(self, addr):
		if addr in self.clients:
			c = self.clients[addr]

		else:
			c = UDPClient(self, addr, self.window_size)
			self.clients[addr] = c

		return c

	def _handle_read(self):
		clients = set() # keep track of delivered clients
		b = BytesIO(self.max_pkt_size)

		while 1:
			n = 0

			try:
				n, addr = self.socket.recvfrom_into(b, self.max_pkt_size)
				b.set_length(n)

			except:
				break # retry later

			if not n:
				continue

			c = self._get_client(addr)
			clients.add(c)
			c.push_bytes(b.read())

		for c in clients:
			# Wake up client socket
			self.io_loop.spawn_callback(self.handle_packet, c)

	def _send(self, bufferio, addr):
		self._outbound_packet.append((bufferio, addr))
		self._add_io_state(self.io_loop.WRITE)

	def _handle_write(self):
		try:
			while self._outbound_packet:
				b, addr = self._outbound_packet[0]
				while b:
					n = self.socket.sendto(b, addr)
					b[:] = b[n:]

				self._outbound_packet.popleft()

			self._remove_io_state(self.io_loop.WRITE)

		except: # retry later
			pass

	def _handle_events(self, fd, events):
		if self.closed():
			return

		if events & self.io_loop.READ:
			self._handle_read()

		if events & self.io_loop.WRITE:
			self._handle_write()

		if events & self.io_loop.ERROR:
			print ('ERROR Event in %s' % self)

	def handle_packet(self, client):
		'''Handle incoming packets here'''

		raise NotImplemented

	def shutdown(self, client):
		'''Shutdown connection to client'''

		raise NotImplemented
