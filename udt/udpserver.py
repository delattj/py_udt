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
	def __init__(self, addr, window_size, sendto):
		self.addr = addr
		self.inbound_packet = deque(maxlen=window_size)
		self.handshaked = False
		self._sendto = sendto
		self._dangling_packet = None

	def send(self, bufferio):
		self._sendto(bufferio, self.addr)

class UDPServer(object):
	def __init__(self, ip_version=AF_INET, ioloop=None,
		max_pkt_size=1500, window_size=25600):

		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self._state = None
		self._read_callback = None # ????
		self.ioloop = ioloop or IOLoop.instance()
		self.port = None
		self.clients = {}
		self.outbound_packet = deque(maxlen=window_size)
		self.window_size = window_size
		self.max_pkt_size = max_pkt_size

	def bind(self, port):
		self.port = port
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.socket.setblocking(0)
		self.socket.bind(('', port))
		self._add_io_state(self.ioloop.READ)

	def start(self):
		IOLoop.instance().start()

	def _add_io_state(self, state):
		if self._state is None:
			self._state = IOLoop.ERROR | state
			self.ioloop.add_handler(
				self.socket.fileno(), self._handle_events, self._state
			)

		elif not self._state & state:
			self._state = self._state | state
			self.ioloop.update_handler(self.socket.fileno(), self._state)

	def _remove_io_state(self, state):
		if self._state is not None and self._state & state:
			self._state ^= state
			self.ioloop.update_handler(self.socket.fileno(), self._state)

	def closed(self):
		return self.socket is None

	def close(self):
		self.ioloop.remove_handler(self.socket.fileno())
		self.socket.shutdown(socket.SHUT_RDWR)
		self.socket.close()
		self.socket = None

	def _get_client(self, addr):
		if addr in self.clients:
			c = self.clients[addr]

		else:
			c = UDPClient(addr, self.window_size, self._send)
			self.clients[addr] = c

		return c

	def _handle_read(self):
		clients = set() # keep track of delivered clients
		while 1:

			try:
				data, addr = self.socket.recvfrom(self.max_pkt_size)

			except:
				break # retry later

			c = self._get_client(addr)
			clients.add(c)
			if data:
				if c._dangling_packet is None:
					b = BytesIO(self.max_pkt_size)
					c._dangling_packet = b

				else:
					b = c._dangling_packet
					remaining = b.size - b.tell()
					if len(data) > remaining:
						# Buffer is overflowing
						b.write(data[:remaining])
						c.inbound_packet.append(b)
						b = BytesIO(self.max_pkt_size)
						data = data[remaining:]

				b.write(data)

		for c in clients:
			c.inbound_packet.append(c._dangling_packet)
			c._dangling_packet = None

			# TODO: queue it in a callback ???
			while c.inbound_packet:
				self.handle_packet(c, c.inbound_packet.popleft())

	def _send(self, bufferio, addr):
		self.outbound_packet.append((bufferio, addr))
		self._add_io_state(self.ioloop.WRITE)

	def _handle_write(self):
		try:
			while self.outbound_packet:
				b, addr = self.outbound_packet[0]
				while b:
					n = self.socket.sendto(b, addr)
					b[:] = b[n:]

				self.outbound_packet.popleft()

			self._remove_io_state(self.ioloop.WRITE)

		except: # retry later
			pass

	def _handle_events(self, fd, events):
		if self.closed():
			return

		if events & self.ioloop.READ:
			self._handle_read()

		if events & self.ioloop.WRITE:
			self._handle_write()

		if events & self.ioloop.ERROR:
			print ('ERROR Event in %s' % self)

	def handle_packet(self, client, bufferio):
		'''Handle incoming packets here'''

		raise NotImplemented
