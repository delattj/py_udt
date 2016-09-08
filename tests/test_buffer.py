import sys
sys.path.append('..')
import udt.buffer

u = udt.buffer.BytesIO(5)
f = udt.buffer.BytesIO(5)

u.write('Bonjour')

assert u.read(5) == 'Bonjo'

f.write(u)
assert f == 'Bonjo'

f[:] = f[1:]

assert f.read() == 'onjo'

print f