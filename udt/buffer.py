
class BytesIO(bytearray):

	def __new__(cls, size):
		self = super(BytesIO, cls).__new__(cls, '\0'*size)
		self.size = size
		self._w_offset = 0
		return self

	def read(self, n=None, start=0):
		n = self._w_offset if n is None else min(n, self._w_offset)
		t = n + start
		return self[min(start, t):t]

	__str__ = read

	def raw(self):
		return self[:]

	def write(self, d, offset=None):
		if offset is None:
			offset = self._w_offset

		len_d = len(d)
		end = min(offset + len_d, self.size)
		d_end = end - offset

		self[offset:end] = d[:d_end] if d_end != len_d else d
		self._w_offset = end

	def seek(self, n):
		self._w_offset = min(n, self.size)

	def tell(self):
		return self._w_offset

