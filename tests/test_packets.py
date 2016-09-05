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
# print b
d = udt.packet.DataPacket()
d.unpack_from(b, 8)

assert d.seq == 1
assert d.msg == 5
assert d.ts == 2
assert d.dst_sock_id == 3
assert d.data == 'Bonjour!'

print handshake
b.seek(0)
handshake.pack_into(b)
# print b
h = udt.packet.HandshakePacket()
h.unpack_from(b)
print h

assert h.header.get_msg_type() == udt.packet.handshake
assert h.sock_addr == '127.0.0.1'


