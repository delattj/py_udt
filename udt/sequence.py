
class SequenceKeeper(object):
	threshold = 0
	max_no = 0

	def __init__(self, max_no):
		self.max_no = max_no
		self.threshold = max_no/2

	def comp(self, a, b):
		d = a - b
		return d if abs(d) < self.threshold else (b - a)

	def incr(self, a):
		return 0 if a == self.max_no else a + 1

	def decr(self, a):
		return self.max_no if a == 0 else a - 1

	def offset(self, a, b):
		d = b - a
		if a <= b or abs(d) < self.threshold:
			return d

		return d + self.max_no + 1

	def len(self, a, b):
		return (b - a) if a <= b else (b - a + self.max_no + 1)


class DictSequence(dict):
	last_read = -1
	seq_no = -1
	keeper = None
	size = 0

	def __init__(self, buffer_size, keeper, start=0):
		self.size = buffer_size
		self.keeper = keeper
		self.last_read = start - 1
		self.seq_no = start - 1

	def __iter__(self):
		no = self.last_read
		size = self.size
		incr = self.keeper.incr
		try:
			for _ in xrange(size):
				no = incr(no)
				next_item = self[no]
				del self[no]
				self.last_read = no
				yield next_item

		except KeyError:
			pass

	def next_seq(self):
		'''Find next iterable sequence'''
		no = self.seq_no
		incr = self.keeper.incr
		for _ in xrange(self.keeper.threshold):
			no = incr(no)
			if no not in self:
				break

			self.seq_no = no

		return self.seq_no

	def has_seq_data(self):
		return self.last_read != self.seq_no

	def add(self, item):
		i = self.keeper.incr(self.seq_no)
		self[i] = item
		self.seq_no = i
		return i



if __name__ == "__main__":
	k = SequenceKeeper(10)
	u = DictSequence(10, k, 10)

	u.add("z")
	u.add("a")
	u.add("b")
	u.add("c")

	print k.offset(9, 3) -1
	print u.next_seq()
	print ''.join(u)
