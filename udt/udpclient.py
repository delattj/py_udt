import os
import errno
import struct
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

# ISWIN = os.name == 'nt'
LINGER = 180

def _set_stack(exc):
	exc.__traceback__ = extract_stack()
	return exc

class BufferFull(Exception):
	pass

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
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self.socket.setblocking(0)
		self._state = None
		self.io_loop = io_loop or IOLoop.instance()
		self.host = host
		self.port = port
		self.flight_flag_size = window_size
		self.mss = mtu - 28 # 28 -> IP header size
		self._outbound_packet = deque(maxlen=50)
		self._inbound_packet = deque(maxlen=500)

		self._waiting_connect = None
		self._waiting_packet = None
		self._waiting_outbound = None

	def start(self):
		IOLoop.instance().start()

	def _add_io_state(self, state):
		if self.closed():
			return

		if self._state is None:
			self._state = IOLoop.ERROR | state
			self.io_loop.add_handler(
				self.socket.fileno(), self._handle_events, self._state
			)

		elif not self._state & state:
			self._state = self._state | state
			self.io_loop.update_handler(self.socket.fileno(), self._state)

	def _remove_io_state(self, state):
		if self.closed():
			return

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
		inbound = self._inbound_packet
		b_left = len(inbound) - inbound.maxlen
		if b_left >= 0:
			return # drop packet

		inbound.append(packet)
		if b_left == -1:
			raise BufferFull()

	@coroutine
	def get_next_packet(self):
		assert self._waiting_packet is None
		# Only one coroutine can wait for incoming packet

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

		except BufferFull:
			pass

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
		outbound = self._outbound_packet
		length = len(outbound)
		if length:
			self._add_io_state(self.io_loop.WRITE)

		if self._waiting_outbound is None:
			return

		if length < outbound.maxlen:
			self._waiting_outbound.set_result(None)
			self._waiting_outbound = None

	def _shutdown_outbound(self):
		if self._waiting_outbound is None:
			return

		self._waiting_outbound.cancel()
		self._waiting_outbound = None

	def _handle_write(self):
		outbound = self._outbound_packet
		window_size = self.flight_flag_size
		try:
			while outbound:
				b = outbound[0]
				window_size -= len(b)
				if window_size <= 0:
					break

				self.socket.send(b)
				outbound.popleft() # remove only if it worked

			self._remove_io_state(self.io_loop.WRITE)

		except socket.error as e:
			if e.args[0] not in _ERRNO_WOULDBLOCK:
				self.close()
				raise

		# Wake up the send buffer after a few millisecond
		# to let the other end to receive data and UDP socket
		# to clear its own internal buffer.
		self.io_loop.call_later(0.01, self._wake_outbound)

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

	def connect(self):
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
