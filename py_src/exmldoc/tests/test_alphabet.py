import unittest
from exmldoc.alphabet import PythonAlphabet

class TestAlphabet(unittest.TestCase):
    def test_alphabet_basic(self):
        alph = PythonAlphabet()
        idx1 = alph[1]
        idx2 = alph['a']
        idx3 = alph[(1,2)]
        idx4 = alph['a']
        self.assertEqual(idx1, 0,
                         'indices must start at 0')
        self.assertEqual(idx2, idx4,
                         'the same object must always get the same index')
        self.assertEqual(idx3 + 1, len(alph),
                         'length should be last index plus one')
        self.assertEqual(list(alph), [1, 'a', (1, 2)],
                         'iteration should return objects in the correct order')