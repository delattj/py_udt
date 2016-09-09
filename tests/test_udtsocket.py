import sys
sys.path.append('..')
import udt.udtsocket
import udt.udpserver


from threading import Thread
from time import sleep

class UDTServer(udt.udpserver.UDPServer):

	def handle_packet(self, client):
		header_size = udt.udtsocket.ControlHeader.size()
		handshake_size = udt.udtsocket.HandshakePacket.size()

		while 1:
			h_buff = client.get_bytes(header_size)
			if h_buff is None:
				break # Not enough bytes to shew

			h = udt.udtsocket.ControlHeader(h_buff)

			if h.get_msg_type() == udt.udtsocket.ControlPacket.handshake:

				hd_buff = client.get_bytes(handshake_size)
				if hd_buff:
					p = udt.udtsocket.HandshakePacket(hd_buff, header=h)
					print "!", p
					p.req_type = 1
					p.header.dst_sock_id = p.sock_id
					bufferio = udt.udtsocket.BytesIO(handshake_size+header_size)
					p.pack_into(bufferio)
					# print udt.udtsocket.HandshakePacket(bufferio)
					client.send(bufferio)


# def server():
# 	import socket

# 	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 	s.bind(('', 47008))
# 	while 1:
# 		b = udt.udtsocket.BytesIO(1500)
# 		(d, addr) = s.recvfrom_into(b, 1500)
# 		if not d: break
# 		print "Recieved from "+ str(addr)
# 		print "###", d
# 		p = udt.udtsocket.HandshakePacket()
# 		b.seek(d)
# 		p.unpack_from(b)
# 		p.req_type = 1
# 		p.header.dst_sock_id = p.sock_id
# 		s.sendto(b.read(), addr)
# 	s.close()

def client():
	sleep(1)

	c = udt.udtsocket.UDTSocket('127.0.0.1', 47008)
	c.connect()

	c.handshake()

	sleep(1)
	s.ioloop.stop()
	s.close()

t = Thread(target=client)
t.start()

s = UDTServer()
s.bind(47008)
s.start()
