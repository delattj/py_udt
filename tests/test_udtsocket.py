import os
import sys
sys.path.append('..')
import udt.udtsocket

from struct import Struct
from tornado.gen import coroutine, sleep

FilePath = Struct('>260s')
Int = Struct('>I')

def remove_padding(s):
	e = s.find('\0')
	if e >= 0:
		s = s[:e]

	return s

c = udt.udtsocket.UDTSocket('127.0.0.1', 47008)

@coroutine
def test():
	try:
		yield c.connect()

		# filename = 'laydown.jpg'
		filename = 'BrokenAge.zip'
		c.send(FilePath.pack(filename))
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
		filename = yield client.recv(FilePath.size)
		filename = remove_padding(filename)
		file_path = os.path.expanduser(
			os.path.join('~', 'Desktop', filename)
		)
		size = os.path.getsize(file_path)
		print "!", filename, size
		client.send(Int.pack(size))
		with open(file_path, 'rb') as f:
			yield client.send_file(f, size)

		# client.send(data)

s = FileUDTServer()
s.bind(47008)

test()

s.start()
# c.start()
