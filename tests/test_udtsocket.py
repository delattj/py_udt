import sys
sys.path.append('..')
import udt.udtsocket

# from threading import Thread
from time import sleep

from tornado.gen import coroutine


c = udt.udtsocket.UDTSocket('127.0.0.1', 47008)

@coroutine
def connect():
	try:
		r = yield c.connect()

	finally:
		c.io_loop.stop()
		s.close()


s = udt.udtsocket.UDTServer()
s.bind(47008)

connect()

s.start()
