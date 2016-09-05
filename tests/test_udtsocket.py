import sys
sys.path.append('..')
import udt.udtsocket


s = udt.udtsocket.UDTSocket('127.0.0.1', 47008)
s.connect()

s.handshake()
