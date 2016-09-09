import sys
sys.path.append('..')
import udt.packet
import udt.buffer

b = udt.buffer.BytesIO(200)
data = udt.packet.DataPacket(seq=1, msg=5, ts=2, dst_sock_id=3, data='Bonjour!')
header = udt.packet.ControlHeader(ts=5, dst_sock_id=8)
handshake = udt.packet.HandshakePacket(req_type=1, sock_addr="127.0.0.1")

print data
data.pack_into(b)
assert (b[0] >> 7) == 0 # Read first bit
d = udt.packet.DataPacket()
d.unpack_from(b)

assert d.seq == 1
assert d.msg == 5
assert d.ts == 2
assert d.dst_sock_id == 3
assert d.data == 'Bonjour!', "Got: %s"% d.data

print handshake
b.set_length(0)
handshake.pack_into(b)
assert (b[0] >> 7) == 1 # Read first bit
# print b
h = udt.packet.HandshakePacket(b)
# h.unpack_from(b)
print h

assert h.header.get_msg_type() == udt.packet.ControlPacket.handshake
assert h.sock_addr == '127.0.0.1', "Got: %s"% h.sock_addr


