class PythonAlphabet(object):
    def __init__(self):
        self.int2obj = []
        self.obj2int = {}

    def __getitem__(self, k):
        if k in self.obj2int:
            return self.obj2int[k]
        else:
            n = len(self.int2obj)
            self.int2obj.append(k)
            self.obj2int[k] = n
            return n

    @property
    def words(self):
        return self.int2obj
