import os
import sys
sys.path.append('..')
import udt.udtsocket

from struct import Struct
from tornado.gen import coroutine, sleep

Int = Struct('>I')

c = udt.udtsocket.UDTSocket('127.0.0.1', 47008)

@coroutine
def test():
	try:
		yield c.connect()

		filename = 'laydown.jpg'
		c.send(filename)
		size = yield c.recv(Int.size)
		size, = Int.unpack(size)
		print "#", size
		file_path = os.path.expanduser(
			os.path.join('~', 'Desktop', 'recieved', filename)
		)
		with open(file_path, 'wb') as f:
			yield c.recv_file(f, size)

		# yield sleep(1)

	finally:
		c.io_loop.stop()
		s.close()
		pass

class FileUDTServer(udt.udtsocket.UDTServer):

	@coroutine
	def on_data_ready(self, client):
		filename = yield client.recv(11)
		print "!", filename
		file_path = os.path.expanduser(
			os.path.join('~', 'Desktop', filename)
		)
		with open(file_path, 'rb') as f:
			size = udt.udtsocket.get_file_size(f)
			print size
			client.send(Int.pack(size))
			client.send_file(f)

		# client.send(data)

s = FileUDTServer()
s.bind(47008)

test()

s.start()
# c.start()
