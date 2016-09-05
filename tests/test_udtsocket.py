import sys
sys.path.append('..')
import udt.udtsocket


from threading import Thread
from time import sleep

def server():
	import socket

	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.bind(('', 47008))
	while 1:
		(d, addr) = s.recvfrom(1024)
		if not d: break
		print "Recieved from "+ str(addr)
		print "###", len(d)
	s.close()

t = Thread(target=server)
t.daemon = True
t.start()
sleep(1)

s = udt.udtsocket.UDTSocket('127.0.0.1', 47008)
s.connect()

s.handshake()
