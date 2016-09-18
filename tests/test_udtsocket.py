import sys
sys.path.append('..')
import udt.udtsocket

from tornado.gen import coroutine, sleep


c = udt.udtsocket.UDTSocket('127.0.0.1', 47008)

@coroutine
def connect():
	try:
		r = yield c.connect()
		# yield sleep(1)

	finally:
		c.io_loop.stop()
		s.close()
		pass


s = udt.udtsocket.UDTServer()
s.bind(47008)

# connect()

s.start()
# c.start()
