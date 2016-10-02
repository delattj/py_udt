import os
import errno
import socket
from collections import deque
from traceback import extract_stack

from tornado.ioloop import IOLoop
from tornado.gen import coroutine, Return, Future

# IP version
AF_INET = socket.AF_INET
AF_INET6 = socket.AF_INET6

# Socket error numbers
_ERRNO_INPROGRESS = (errno.EINPROGRESS,)
if hasattr(errno, "WSAEINPROGRESS"):
	_ERRNO_INPROGRESS += (errno.WSAEINPROGRESS,)

_ERRNO_WOULDBLOCK = (errno.EWOULDBLOCK, errno.EAGAIN)
if hasattr(errno, "WSAEWOULDBLOCK"):
	_ERRNO_WOULDBLOCK += (errno.WSAEWOULDBLOCK,)

def _set_stack(exc):
	exc.__traceback__ = extract_stack()
	return exc

class Shutdown(Exception):
	pass

class Cancel(Exception):
	pass

class FutureExt(Future):

	def cancel(self):
		self.set_exception(Cancel())

	def cancelled(self):
		return isinstance(self.exception(), Cancel)

class UDPSocket(object):
	def __init__(self, host, port, ip_version=AF_INET, io_loop=None,
		mtu=1500, window_size=25600):

		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.socket.setblocking(0)
		self._state = None
		self.io_loop = io_loop or IOLoop.instance()
		self.host = host
		self.port = port
		self.reuse_addr = True
		self.flight_flag_size = window_size
		self.mss = mtu - 28 # 28 -> IP header size
		self._outbound_packet = deque(maxlen=window_size)
		self._inbound_packet = deque(maxlen=window_size)

		self._waiting_connect = None
		self._waiting_packet = None
		self._waiting_outbound = None

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

	def connected(self):
		return self._state is not None and self._waiting_connect is None

	def close(self):
		self.on_close()
		self._shutdown_get_next_packet()
		self._shutdown_outbound()
		self.io_loop.remove_handler(self.socket.fileno())
		self.socket.shutdown(socket.SHUT_RDWR)
		self.socket.close()
		self.socket = None

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
			f = FutureExt()
			self._waiting_packet = f
			yield f

		b = self._inbound_packet.popleft()

		raise Return(b)

	def _wake_get_next_packet(self):
		if self._waiting_packet is None:
			return

		if not self._inbound_packet:
			return

		self._waiting_packet.set_result(None)
		self._waiting_packet = None

	def _shutdown_get_next_packet(self):
		if self._waiting_packet is None:
			return

		self._waiting_packet.cancel()
		self._waiting_packet = None

	def _handle_read(self):
		try:
			while 1:

				b = self.socket.recv(self.mss)

				if not b:
					continue

				self.push_packet(b)

		except socket.error as e:
			if e.args[0] not in _ERRNO_WOULDBLOCK:
				self.close()
				raise

		self._wake_get_next_packet()

	def write(self, data):
		if self._waiting_outbound is not None:
			return self._waiting_outbound

		out = self._outbound_packet
		if len(out) == out.maxlen:
			# Buffer is full, return a future for future notification
			f = FutureExt()
			self._waiting_outbound = f
			return f

		out.append(data)
		self._add_io_state(self.io_loop.WRITE)

	def _wake_outbound(self):
		if self._waiting_outbound is None:
			return

		outbound = self._outbound_packet
		if len(outbound) < outbound.maxlen:
			self._waiting_outbound.set_result(None)
			self._waiting_outbound = None

	def _shutdown_outbound(self):
		if self._waiting_outbound is None:
			return

		self._waiting_outbound.cancel()
		self._waiting_outbound = None

	def _handle_write(self):
		outbound = self._outbound_packet
		try:
			while outbound:
				b = outbound[0]
				self.socket.send(b)
				outbound.popleft() # remove only if it worked

			self._remove_io_state(self.io_loop.WRITE)

		except socket.error as e:
			if e.args[0] not in _ERRNO_WOULDBLOCK:
				self.close()
				raise

		self._wake_outbound()

	def _handle_events(self, fd, events):
		if self.closed():
			return

		if self._waiting_connect is not None:
			self._handle_connect()

		if events & self.io_loop.READ:
			self._handle_read()

		if events & self.io_loop.WRITE:
			self._handle_write()

		if events & self.io_loop.ERROR:
			print ('ERROR Event in %s' % self)

	def set_reuse_addr(self):
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	def connect(self):
		if self.reuse_addr:
			self.set_reuse_addr()

		f = self._waiting_connect = Future()

		err = self.socket.connect_ex((self.host, self.port))
		if err != 0 and err not in _ERRNO_INPROGRESS\
				and err not in _ERRNO_WOULDBLOCK:
			error = _set_stack(socket.error(err, os.strerror(err)))
			f.set_exception(error)
			self.close()
			return f

		self._add_io_state(self.io_loop.WRITE)

		return f

	def _handle_connect(self):
		err = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
		if err != 0:
			error = _set_stack(socket.error(err, os.strerror(err)))
			self._waiting_connect.set_exception(error)
			self.close()
			return

		if not self._outbound_packet:
			self._remove_io_state(self.io_loop.WRITE)

		self._add_io_state(self.io_loop.READ)

		self._waiting_connect.set_result(self)
		self._waiting_connect = None

	def on_close(self):
		'''On close event'''

		raise NotImplemented
