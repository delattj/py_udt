import errno
import socket
from collections import deque

from tornado.ioloop import IOLoop

from .buffer import BytesIO

# IP version
AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6

class UDPClient(object):
	def __init__(self, addr, window_size, outbound_packet):
		self.addr = addr
		self.inbound_packet = deque(maxlen=window_size)
		self.handshaked = False
		self.outbound_packet = outbound_packet
		self._dangling_packet = None

	def send(self, bufferio):
		self.outbound_packet.append((bufferio, self.addr))

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
			c = UDPClient(addr, self.window_size, self.outbound_packet)
			self.clients[addr] = c
			self._add_io_state(self.ioloop.WRITE)

		return c

	def _handle_read(self):
		while 1:

			try:
				data, addr = self.socket.recvfrom(self.max_pkt_size)

			except:
				data = ''

			if not data: # retry later
				break

			c = self._get_client(addr)
			if c._dangling_packet is None:
				b = BytesIO(self.max_pkt_size)

			else:
				b = c._dangling_packet

			b_missing = self.max_pkt_size - b.tell()
			if len(data) > b_missing:
				b.write(data[:b_missing])
				c.inbound_packet.append(b)
				data = data[b_missing:]
				b = BytesIO(self.max_pkt_size)

			b.write(data)

			if b.tell() != self.max_pkt_size:
				c._dangling_packet = b

			else:
				c._dangling_packet = None
				c.inbound_packet.append(b)

			# TODO: queue it in a callback ???
			while c.inbound_packet:
				self.handle_packet(c, c.inbound_packet.popleft())


	def _handle_write(self):
		try:
			while self.outbound_packet:
				addr, b = self.outbound_packet[0]
				while b:
					n = self.socket.sendto(addr, b)
					b = b[n:]

				self.outbound_packet.popleft()

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
