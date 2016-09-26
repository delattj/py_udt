import sys
sys.path.append('..')
import udt.udtsocket

from tornado.gen import coroutine, sleep


c = udt.udtsocket.UDTSocket('127.0.0.1', 47008)

@coroutine
def test():
	try:
		r = yield c.connect()
		s_client = s.clients.values()[0]

		c.send("ABCDEFGHIJKLMNOP")
		data = yield s_client.recv(16)
		print data

		s_client.send("ABCDEFGHIJKLMNOP")
		data = yield c.recv(16)
		print data

	finally:
		c.io_loop.stop()
		s.close()
		pass


s = udt.udtsocket.UDTServer()
s.bind(47008)

test()

s.start()
# c.start()
