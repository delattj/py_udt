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
s.start()

