
class BytesIO(bytearray):

	def __new__(cls, source):
		if isinstance(source, int):
			self = super(BytesIO, cls).__new__(cls, '\0'*source)
			self.size = source
			self._w_offset = 0

		else:
			self = super(BytesIO, cls).__new__(cls, source)
			self.size = len(source)
			self._w_offset = len(source)

		return self

	def read(self, n=None, start=0):
		t = self._w_offset if n is None else min(n, (self._w_offset - start)) + start

		# return BytesIO(self[min(start, t):t])
		return self[min(start, t):t]

	def __str__(self):
		# return super(BytesIO, self).__str__()
		return str(self.read())

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

