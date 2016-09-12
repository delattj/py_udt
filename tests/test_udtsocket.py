import sys
sys.path.append('..')
import udt.udtsocket
import udt.udpserver

from threading import Thread
from time import sleep

def retry_onfail(handler):
	def _fnc(s, client, *args):
		if not handler(s, client, *args):
			client._packet_handler = (handler, args)
			return 0

		client._packet_handler = None
		return 1

	return _fnc

class UDTServer(udt.udpserver.UDPServer):

	def handle_packet(self, client):
		if hasattr(client, '_packet_handler')\
				and client._packet_handler is not None:
			# resume after running out of bytes
			handler, args = client._packet_handler
			if not handler(self, client, *args):
				return

		while 1:
			header_size = udt.udtsocket.ControlHeader.size()
			h_buff = client.get_bytes(header_size)
			if h_buff is None:
				break # Not enough bytes to shew

			if udt.udtsocket.bit_flag_from_byte(h_buff[0]):
				# Control packet

				h = udt.udtsocket.ControlHeader(h_buff)

				c_handler = self.control_handler.get(h.get_msg_type(),
					lambda *a:1)
				if not c_handler(self, client, h):
					break

			else:
				# Data Packet
				pass

	@retry_onfail
	def handle_handshake(self, client, header):
		handshake_size = udt.udtsocket.HandshakePacket.size()

		hd_buff = client.get_bytes(handshake_size)
		if hd_buff:
			p = udt.udtsocket.HandshakePacket(hd_buff, header=header)
			print "!", p

				p.header.dst_sock_id = p.sock_id
				p.syn_cookie = 111 # client.syn_cookie
				bufferio = p.pack()
				client.send(bufferio)

			elif p.req_type > 0:
				print "> Acknowledge handshake"

			elif p.syn_cookie == 111: # client.syn_cookie
				self.handshake = True
				print "> Handshake accepted"

			return 1

	control_handler = {
		udt.udtsocket.ControlPacket.handshake: handle_handshake
	}


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
