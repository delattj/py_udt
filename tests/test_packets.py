import sys
sys.path.append('..')
import udt.packet

data = udt.packet.DataPacket(seq=1, msg=5, ts=2, dst_sock_id=3, data='Bonjour!')
header = udt.packet.ControlHeader(ts=5, dst_sock_id=8)
handshake = udt.packet.HandshakePacket(req_type=1, sock_addr="127.0.0.1")

print data
b = data.pack()
assert udt.packet.bit_flag_from_byte(b[0]) == 0 # Read first bit
d = udt.packet.DataPacket()
d.unpack(b)

assert d.seq == 1
assert d.msg == 5
assert d.ts == 2
assert d.dst_sock_id == 3
assert d.data == 'Bonjour!', "Got: %s"% d.data

print handshake
b = handshake.pack()
assert udt.packet.bit_flag_from_byte(b[0]) == 1 # Read first bit
h = udt.packet.HandshakePacket(b)
print h

assert h.header.get_msg_type() == udt.packet.ControlPacket.handshake
assert h.sock_addr == '127.0.0.1', "Got: %s"% h.sock_addr


