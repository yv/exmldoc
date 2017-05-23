# coding=utf-8
import unittest
from mock import mock_open, patch
import exmldoc

sample_doc=u'''<?xml version="1.0" encoding="utf-8"?>
<exml-doc>
<schema>
<node name="topic">
</node>
</schema>
<body serialization="inline">
<text>
<sentence>
<topic>
<word form="This"/>
<word form="is"/>
<word form="a"/>
</topic>
<word form="sentence"/>
<word form="."/>
</sentence>
<topic>
<sentence>
<word form="No"/>
<word form="object"/>
<word form="has"/>
<word form="an"/>
<word form="ID"/>
<word form="."/>
</sentence>
<sentence>
<word form="Ümläüts"/>
<word form="and"/>
<word form="&#8220;non&#8221;-ISO"/>
<word form="(╯°□°）╯︵┻━┻"/>
<word form="work"/>
<word form="."/>
</sentence>
</topic>
</text>
</body>
</exml-doc>
'''.encode('utf-8')

sample_text_unicode = u'This is a sentence . No object has an ID . Ümläüts and “non”-ISO (╯°□°）╯︵┻━┻ work .'
sample_text_latin = u'This is a sentence . No object has an ID . Ümläüts and "non"-ISO (+°#°)+(+-+ work .'
sample_text_ascii = b'This is a sentence . No object has an ID . Umlauts and "non"-ISO (+deg#deg)+(+-+ work .'


class TestEXML(unittest.TestCase):
    def test_general(self):
        m = mock_open(read_data=sample_doc)
        with patch('exmldoc.open', m):
            doc = exmldoc.load('fake_data.exml.xml')
        m.assert_called_once_with('fake_data.exml.xml', 'rb')
        self.assertEqual(
            len(doc), 17,
            'length should be number of words')
        self.assertEqual(
            len(doc.get_objects_by_class(exmldoc.tree.Tree)), 3,
            'should read three sentences objects')
        self.assertEqual(
            len(doc.get_objects_by_level('sentence')), 3,
            'should read three sentence markables')
        self.assertEqual(
            len(doc.get_objects_by_level('text')), 1,
            'should read one text markable')
        self.assertEqual(
            len(doc.get_objects_by_level('topic')), 2,
            'should read two topic markables')

    def test_unicode(self):
        m = mock_open(read_data=sample_doc)
        with patch('exmldoc.open', m):
            doc = exmldoc.load('fake_data.exml.xml')
        self.assertEqual(
            doc.words,
            sample_text_unicode.split(),
            'unicode mode should produce unicode words')
        self.assertEqual(
            [term.word for term in doc.w_objs],
            sample_text_unicode.split(),
            'unicode mode should produce unicode term.words')

    def test_utf8(self):
        m = mock_open(read_data=sample_doc)
        with patch('exmldoc.open', m):
            doc = exmldoc.load('fake_data.exml.xml', encoding='utf-8')
        self.assertEqual(
            doc.words,
            sample_text_unicode.encode('utf-8').split(),
            'utf-8 mode should produce utf-8 word forms')
        self.assertEqual(
            [term.word for term in doc.w_objs],
            sample_text_unicode.encode('utf-8').split(),
            'utf-8 mode should produce utf-8 term.words')

    def test_latin1(self):
        m = mock_open(read_data=sample_doc)
        with patch('exmldoc.open', m):
            doc = exmldoc.load('fake_data.exml.xml', encoding='latin1')
        self.assertEqual(
            doc.words,
            sample_text_latin.encode('ISO-8859-15', 'ignore').split(),
            'latin1 mode should produce latin1 word forms')
        self.assertEqual(
            [term.word for term in doc.w_objs],
            sample_text_latin.encode('ISO-8859-15', 'ignore').split(),
            'latin1 mode should produce latin1 term.words')

    def test_ascii(self):
        m = mock_open(read_data=sample_doc)
        with patch('exmldoc.open', m):
            doc = exmldoc.load('fake_data.exml.xml', encoding='ascii')
        self.assertEqual(
            doc.words,
            sample_text_ascii.split(),
            'ascii mode should produce ascii word forms')
        self.assertEqual(
            [term.word for term in doc.w_objs],
            sample_text_ascii.split(),
            'ascii mode should produce ascii term.words')
