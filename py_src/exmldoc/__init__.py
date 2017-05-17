#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
exmldoc contains code related to the ExportXMLv2 format, including
the object model for corpus schemata, functions to write out corpora
in XML and JSON formats, and functions to read single documents or corpora
in JSON format.
"""
from __future__ import print_function

import sys
import regex
from isounidecode import unidecode
from exmldoc import tree
from exmldoc.topsort import topsort
from exmldoc.alphabet import PythonAlphabet
from collections import OrderedDict, defaultdict
from itertools import izip, islice
from xml.sax.saxutils import quoteattr, escape
import xml.etree.cElementTree as etree
import simplejson as json


class _EmptyClass:
    pass


__version__ = "2014-07-08"
__author__ = "Yannick Versley / Univ. Heidelberg"

QNAME_XML_ID = '{http://www.w3.org/XML/1998/namespace}id'

if sys.version_info.major >= 3:
    intern = sys.intern
    xrange = range


def create_id(prefix, alphabet):
    n0 = len(alphabet)
    n = n0
    while alphabet['%s%d' % (prefix, n)] < n0:
        n += 1
    return '%s%d' % (prefix, n)


class TextAttribute:

    """
    an attribute with a string value
    """

    def __init__(self, name, prop_name=None, default_val=None):
        self.name = name
        if prop_name is None:
            self.prop_name = name
        else:
            self.prop_name = prop_name
        self.default_val = default_val

    def map_attr(self, val, doc):
        if val == self.default_val:
            return None
        return val

    def unmap_attr(self, val, doc, encoding):
        return unmunge_xml(val, encoding)

    def get_updown(self, obj, doc, result):
        pass

    def describe_schema(self, f, encoding=None):
        open_tag(f, 'text-attr', [('name', self.name)],
                 indent=2, encoding=encoding)
        f.write('/>\n')


class EnumAttribute(TextAttribute):
    """
    an attribute with a value that comes from an
    enumeration. In the XML format, all declared enumeration
    values are listed in the schema header.
    """

    def __init__(self, name, **kw):
        TextAttribute.__init__(self, name, **kw)
        self.alphabet = PythonAlphabet()
        self.descriptions = {}

    def add_item(self, name, description=None):
        self.alphabet[name]
        if description is not None:
            self.descriptions[name] = description

    def describe_schema(self, f, encoding=None):
        open_tag(f, 'enum-attr', [('name', self.name)],
                 indent=2, encoding=encoding)
        f.write('>\n')
        for val in self.alphabet.words:
            atts = [('name', val)]
            if val in self.descriptions:
                atts.append(('description', self.descriptions[val]))
            open_tag(f, 'val', atts,
                     indent=3, encoding=encoding)
            f.write('/>\n')
        f.write('  </enum-attr>\n')


class RefAttribute:
    """
    an attribute containing a reference to another
    object (terminal or markable).
    """

    def __init__(self, name, prop_name=None, restriction=None,
                 restrict_target=None):
        self.name = name
        if prop_name is None:
            self.prop_name = self.name
        else:
            self.prop_name = prop_name
        if restriction is None or restriction == 'none':
            self.restriction = None
        else:
            self.restriction = intern(restriction)
        self.restrict_target = restrict_target

    def map_attr(self, val, doc):
        return doc.get_obj_id(val)

    def unmap_attr(self, val, doc, encoding=None):
        return doc.object_by_id[val]

    def get_updown(self, obj, doc, result):
        if self.restriction is 'down':
            other_obj = getattr(obj, self.prop_name)
            if other_obj is not None:
                result.append((doc.get_obj_id(obj),
                               doc.get_obj_id(other_obj)))
        elif self.restriction is 'up':
            other_obj = getattr(obj, self.prop_name)
            if other_obj is not None:
                result.append((doc.get_obj_id(other_obj),
                               doc.get_obj_id(obj)))

    def describe_schema(self, f, encoding=None):
        open_tag(f, 'node-ref', [('name', self.name)],
                 indent=2, encoding=encoding)
        f.write('/>\n')

class IDRefAttribute:

    """
    an attribute containing the string ID of another
    terminal or node
    """

    def __init__(self, name, prop_name=None, restriction=None,
                 restrict_target=None):
        self.name = name
        if prop_name is None:
            self.prop_name = self.name
        else:
            self.prop_name = prop_name
        if restriction is None or restriction == 'none':
            self.restriction = None
        else:
            self.restriction = sys.intern(restriction)
        self.restrict_target = restrict_target

    def map_attr(self, val, doc):
        return val

    def unmap_attr(self, val, doc, encoding):
        return val

    def get_updown(self, obj, doc, result):
        if self.restriction is 'down':
            other = getattr(obj, self.prop_name)
            if other is not None:
                result.append((doc.get_obj_id(obj),
                               other))
        elif self.restriction is 'up':
            other = getattr(obj, self.prop_name)
            if other is not None:
                result.append((other,
                               doc.get_obj_id(obj)))

    def describe_schema(self, f, encoding=None):
        open_tag(f, 'node-ref', [('name', self.name)],
                 indent=2, encoding=encoding)
        f.write('/>\n')

class MarkableSchema:

    """
    a document schema that describes the mapping from Python
    objects and attributes to nodes in the serialization.
    """

    def __init__(self, name, cls=None, kind="Markable"):
        self.name = name
        self.attributes = []
        self.init_attrs = []
        self.edges = []
        self.interfaces = set()
        self.cls = cls
        self.locality = None
        self.suffix = kind

    def serialize_object(self, obj, doc):
        oid = doc.get_obj_id(obj)
        span = obj.span
        attr_d = OrderedDict()
        attr_d['xml:id'] = oid
        for att in self.attributes:
            if hasattr(obj, att.prop_name):
                v = getattr(obj, att.prop_name)
                if v is not None:
                    v_txt = att.map_attr(v, doc)
                    if v_txt is not None:
                        attr_d[att.name] = v_txt
        edges = []
        for edge_schema in self.edges:
            edgelist = edge_schema.get_edges(obj, doc)
            for edgevals in edgelist:
                attr_e = OrderedDict()
                for (att, val) in izip(edge_schema.attributes, edgevals):
                    if val is not None:
                        attr_e[att.name] = att.map_attr(val, doc)
                edges.append((edge_schema.name, attr_e))
        return (span, self.name, attr_d, edges)

    def make_json(self, obj, doc):
        oid = doc.get_obj_id(obj)
        attrs = {'_id': oid, 'span': obj.span}
        for att in self.attributes:
            if hasattr(obj, att.prop_name):
                v = getattr(obj, att.prop_name)
                if v is not None:
                    attrs[att.name] = munge_json(v)
        for edge in self.edges:
            v = edge.get_edges(obj, doc)
            if v:
                attrs[edge.name] = munge_json(v)
        return attrs

    def create_from_json(self, obj, doc):
        args = []
        for att in self.init_attrs:
            v = None
            try:
                v = unmunge_json(obj[att.prop_name], doc)
            except KeyError:
                pass
            args.append(v)
        try:
            m = self.cls(*args)
        except TypeError:
            print("Cannot instantiate %s" % (self.cls), file=sys.stderr)
            raise
        m.xml_id = obj['_id']
        m.span = obj['span']
        doc.object_by_id[m.xml_id] = m
        return m

    def create_from_xml(self, elem, doc, encoding=None):
        args = []
        for att in self.init_attrs:
            v = None
            try:
                v = unmunge_xml(elem.attrib[att.prop_name], encoding)
            except KeyError:
                pass
            args.append(v)
        try:
            m = self.cls(*args)
        except TypeError:
            print("Cannot instantiate %s" % (self.cls), file=sys.stderr)
            raise
        m.xml_id = elem.attrib[QNAME_XML_ID]
        doc.object_by_id[m.xml_id] = m
        return m

    def fill_from_json(self, obj, attrs, doc):
        for att in self.attributes:
            if att.name in attrs:
                setattr(obj, att.prop_name, unmunge_json(attrs[att.name], doc))
        for edge in self.edges:
            if edge.name in attrs:
                edge.set_edges(obj, unmunge_json(attrs[edge.name], doc), doc)

    def fill_from_xml(self, obj, elem, doc, encoding):
        for att in self.attributes:
            if att.name in elem.attrib:
                setattr(obj, att.prop_name,
                        att.unmap_attr(elem.attrib[att.name], doc, encoding))
        if 'span' in elem.attrib:
            obj.span = decode_span(elem.attrib['span'], doc)

    def get_updown(self, obj, doc, result):
        for att in self.attributes:
            att.get_updown(obj, doc, result)
        for edge in self.edges:
            edge.get_updown(obj, doc, result)

    def describe_schema(self, f, edges, encoding=None):
        attrs = [('name', self.name)]
        if self.locality is not None:
            attrs.append(('locality', self.locality))
        open_tag(f, 'node', attrs, 1, encoding=encoding)
        f.write('>\n')
        for att in self.attributes:
            att.describe_schema(f, encoding=encoding)
        f.write(' </node>\n')
        for edge_schema in self.edges:
            if edge_schema.name not in edges:
                edges[edge_schema.name] = [edge_schema, [self.name]]
            else:
                edges[edge_schema.name][1].append(self.name)

    def check_interface(self, name, descr):
        result = []
        for (tp, part) in descr:
            try:
                if tp == 'attr':
                    att = self.attribute_by_name(part)
                elif tp == 'edge':
                    att = self.edge_by_name(part)
                else:
                    assert False, tp
                result.append((tp, att))
            except KeyError:
                print("No %s" % (part,), file=sys.stderr)
                return False
        self.interfaces.add(name)
        return result

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def edge_by_name(self, name):
        for edge in self.edges:
            if edge.name == name:
                return edge
        raise KeyError(name)

    def add_edge(self, edge):
        self.edges.append(edge)


class SecondaryEdges:

    def __init__(self, name):
        self.name = name
        self.alphabet = PythonAlphabet()
        self.attributes = [EnumAttribute('cat'),
                           RefAttribute('parent',
                                        restrict_target=['word', 'node'])]
        self.suffix = 'Edge'
        self.descriptions = {}

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def get_edges(self, obj, doc):
        edges = []
        if hasattr(obj, 'secedge') and obj.secedge is not None:
            for secedge in obj.secedge:
                edges.append([secedge[0], secedge[1]])
        return edges

    def set_edges(self, obj, vals, doc):
        obj.secedge = vals

    def get_updown(self, obj, doc, result):
        pass

    def add_item(self, name, description=None):
        self.alphabet[name]
        if description is not None:
            self.descriptions[name] = description


def decode_span(s_span, doc):
    # TODO reject invalid word_ids
    result = []
    for s_part in s_span.split(','):
        if '..' in s_part:
            (s_start, s_end) = s_part.split('..', 2)
            start = doc.word_ids[s_start]
            end = doc.word_ids[s_end] + 1
            result += [start, end]
        else:
            start = doc.word_ids[s_part]
            result += [start, start + 1]
    return result


def open_tag(f, name, items, indent=0, encoding=None):
    f.write(' ' * indent)
    f.write('<%s' % (name,))
    for k, v in items:
        if v is None:
            continue
        if isinstance(v, unicode) and encoding is not None:
            f.write(' %s="%s"' %
                    (k, escape(v.encode(encoding), {'"': "&quot;"})))
        else:
            f.write(' %s=%s' % (k, quoteattr(v)))


class ChildEdges:

    def __init__(self, name):
        self.name = name
        self.attributes = [RefAttribute('target'),
                           TextAttribute('label')]
        self.suffix = 'Edge'

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def put_edges(self, obj, doc, edges):
        for n in obj.children:
            attr_d = OrderedDict()
            attr_d['target'] = doc.get_obj_id(n)
            attr_d['label'] = n.edge_label
            edges.append((self.name, attr_d))

    def get_updown(self, obj, doc, result):
        obj_id = doc.get_obj_id(obj)
        for n in obj.children:
            result.append((doc.get_obj_id(n),
                           obj_id))


class ReferenceEdges(object):

    def __init__(self, name):
        self.name = name
        self.attributes = [EnumAttribute('type'),
                           IDRefAttribute('target',
                                          restrict_target=['word', 'node'])]
        self.suffix = 'Edge'

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def get_edges(self, obj, doc):
        info = getattr(obj, 'anaphora_info', None)
        if info is not None:
            tgt = None
            if info[0] == 'split_antecedent':
                return []
            elif info[0] not in ['expletive', 'inherent_reflexive']:
                tgt = ' '.join(info[1])
                # tgt=info[1]
            return [[info[0], tgt]]
        else:
            return []

    def set_edges(self, obj, vals, doc):
        assert len(vals) == 1
        kind = vals[0][0]
        if len(vals[0]) > 1 and vals[0][1] is not None:
            targets = vals[0][1].split(' ')
        else:
            targets = None
        obj.anaphora_info = [kind, targets]

    def get_updown(self, obj, doc, result):
        pass


class GenericEdges(object):
    def __init__(self, name, prop_name=None):
        self.name = name
        if prop_name is None:
            self.prop_name = name
        else:
            self.prop_name = prop_name
        self.attributes = []
        self.suffix = 'Edge'

    def find_attribute(self, name):
        for i, att in enumerate(self.attributes):
            if att.name == name:
                return i, att
        raise KeyError(name)

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def get_edges(self, obj, doc):
        if hasattr(obj, self.prop_name):
            return getattr(obj, self.prop_name)
        else:
            return []

    def set_edges(self, obj, vals, doc):
        setattr(obj, self.prop_name, vals)

    def get_updown(self, obj, doc, result):
        pass


class SplitRefEdges(object):

    def __init__(self, name):
        self.name = name
        self.attributes = [EnumAttribute('type'),
                           TextAttribute('target')]
        self.suffix = 'Edge'

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def get_edges(self, obj, doc):
        info = getattr(obj, 'anaphora_info', None)
        if info is not None:
            tgt = None
            if info[0] == 'split_antecedent':
                tgt = ' '.join(info[1])
                return [[info[0], tgt]]
            else:
                return []
        else:
            return []

    def set_edges(self, obj, vals, doc):
        assert len(vals) == 1
        kind = vals[0][0]
        targets = vals[0][1].split(' ')
        obj.anaphora_info = [kind, targets]

    def get_updown(self, obj, doc, result):
        pass


def munge_json(obj):
    if isinstance(obj, list) or isinstance(obj, tuple):
        return map(munge_json, obj)
    elif isinstance(obj, int) or isinstance(obj, unicode):
        return obj
    elif isinstance(obj, str):
        return obj.decode('ISO-8859-15')
    elif hasattr(obj, 'xml_id'):
        return {'_id': obj.xml_id}
    elif obj is None:
        return None
    assert False, obj


# TODO: \u0219 \u2022
uc_dash = regex.compile(u'[\u2010\u2012\u2013\u2014\u2015\u2212]')
uc_squo = regex.compile(u'[\u2018\u2019\u201a\u2032\u02b9\u2039\u203a]')
uc_dquo = regex.compile(u'[\u201c\u201d\u201e\u2033\u02ba]')
uc_bullet = regex.compile(u'[\u2022\u2020\u2021]')


def normalize_string(s):
    s = uc_dash.sub(u'-', s)
    s = uc_squo.sub(u"'", s)
    s = uc_dquo.sub(u'"', s)
    s = uc_bullet.sub(u'*', s)
    return s


def unmunge_json(obj, doc):
    if isinstance(obj, list) or isinstance(obj, tuple):
        return [unmunge_json(x, doc) for x in obj]
    elif isinstance(obj, int):
        return obj
    elif isinstance(obj, unicode):
        return unidecode(normalize_string(obj), 'iso8859-1')
    elif isinstance(obj, str):
        return obj
    elif obj is None:
        return obj
    elif '_id' in obj:
        return doc.object_by_id[obj['_id']]
    assert False, obj


def unmunge_xml(obj, encoding):
    if isinstance(obj, unicode):
        if encoding is None:
            return obj
        elif encoding == 'UTF-8':
            return obj.encode(encoding)
        else:
            return unidecode(normalize_string(obj), encoding)
    else:
        return obj


def to_string(s):
    if isinstance(s, unicode):
        return unidecode(normalize_string(s), 'iso8859-1')
    elif isinstance(s, str):
        return s


class TerminalSchema(object):

    """
    The class for Terminal schema objects
    """

    def __init__(self, name, cls):
        self.name = name
        self.attributes = []
        self.edges = []
        self.interfaces = set()
        self.cls = cls

    def serialize_terminal(self, obj, doc):
        oid = doc.get_obj_id(obj)
        # span=obj.span
        attr_d = OrderedDict()
        attr_d['xml:id'] = oid
        for att in self.attributes:
            if hasattr(obj, att.prop_name):
                v = getattr(obj, att.prop_name)
                if v is not None:
                    v_txt = att.map_attr(v, doc)
                    if v_txt is not None:
                        attr_d[att.name] = v_txt
        edges = []
        for edge_schema in self.edges:
            edgelist = edge_schema.get_edges(obj, doc)
            for edgevals in edgelist:
                attr_e = OrderedDict()
                for (att, val) in izip(edge_schema.attributes, edgevals):
                    if val is not None:
                        attr_e[att.name] = att.map_attr(val, doc)
                edges.append((edge_schema.name, attr_e))
        return (self.name, attr_d, edges)

    def make_json(self, obj, doc):
        oid = doc.get_obj_id(obj)
        attrs = {'_id': oid}
        for att in self.attributes:
            if hasattr(obj, att.prop_name):
                v = getattr(obj, att.prop_name)
                if v is not None:
                    attrs[att.name] = munge_json(v)
        for edge in self.edges:
            v = edge.get_edges(obj, doc)
            if v:
                attrs[edge.name] = munge_json(v)
        return attrs

    def create_from_json(self, attrs, doc):
        # special case: cat/pos is filled or None, word/form MUST be filled
        obj = self.cls(attrs.get('pos'), to_string(attrs['form']))
        if '_id' in attrs:
            s_id = attrs['_id']
            obj.xml_id = s_id
            doc.object_by_id[s_id] = obj
        return obj

    def create_from_xml(self, node, doc, encoding=None):
        obj = self.cls(node.attrib['pos'],
                       unmunge_xml(node.attrib['form'], encoding))
        if QNAME_XML_ID in node.attrib:
            obj.xml_id = node.attrib[QNAME_XML_ID]
        return obj

    def fill_from_json(self, obj, attrs, doc):
        for att in self.attributes:
            if att.name in attrs:
                setattr(obj, att.prop_name, unmunge_json(attrs[att.name], doc))
        for edge in self.edges:
            if edge.name in attrs:
                edge.set_edges(obj, unmunge_json(attrs[edge.name], doc), doc)

    def fill_from_xml(self, obj, node, doc, encoding):
        for att in self.attributes:
            if att.name in node.attrib:
                setattr(obj, att.prop_name,
                        att.unmap_attr(node.attrib[att.name], doc, encoding))

    def describe_schema(self, f, edges, encoding=None):
        open_tag(f, 'tnode', [('name', self.name)], 1,
                 encoding=encoding)
        f.write('>\n')
        for att in self.attributes:
            att.describe_schema(f, encoding=encoding)
        f.write(' </tnode>\n')
        for edge_schema in self.edges:
            if edge_schema.name not in edges:
                edges[edge_schema.name] = [edge_schema, [self.name]]
            else:
                edges[edge_schema.name][1].append(self.name)

    def check_interface(self, name, descr):
        result = []
        for (tp, part) in descr:
            try:
                if tp == 'attr':
                    att = self.attribute_by_name(part)
                elif tp == 'edge':
                    att = self.edge_by_name(part)
                else:
                    assert False, tp
                result.append((tp, att))
            except KeyError:
                print("No %s" % (part,), file=sys.stderr)
                return False
        self.interfaces.add(name)
        return result

    def attribute_by_name(self, att_name):
        for att in self.attributes:
            if att.name == att_name:
                return att
        raise KeyError(att_name)

    def add_attribute(self, att):
        self.attributes.append(att)

    def edge_by_name(self, name):
        for edge in self.edges:
            if edge.name == name:
                return edge
        raise KeyError(name)

    def add_edge(self, edge):
        self.edges.append(edge)


class Document:

    """
    represents an ExportXMLv2 document, including
    words, terminals and markables on different
    annotation layers.
    """

    def __init__(self, t_schema, schemas):
        self.t_schema = t_schema
        self.schemas = schemas
        self.schema_by_class = {}
        self.object_by_id = {}
        # self.basedata=BaseData()
        self.words = []
        self.w_objs = []
        self.word_attr = 'word'
        self.markables_by_start = defaultdict(list)
        self.node_objs = defaultdict(list)
        self.word_ids = PythonAlphabet()
        self.interface_classes = defaultdict(list)
        self.interface_attrs = {}
        if t_schema.cls is not None:
            self.schema_by_class[t_schema.cls] = t_schema
        for schema in schemas:
            if schema.cls is not None:
                self.schema_by_class[schema.cls] = schema

    def add_schemas(self, schemas):
        self.schemas += schemas
        for schema in schemas:
            if schema.cls is not None:
                self.schema_by_class[schema.cls] = schema

    def schema_by_name(self, name):
        for schema in self.schemas:
            if schema.name == name:
                return schema
        raise KeyError

    def add_interface(self, name, spec):
        result = self.t_schema.check_interface(name, spec)
        if result:
            self.interface_classes[name].append('word')
            self.interface_attrs[name] = result
        for schema in self.schemas:
            result = schema.check_interface(name, spec)
            if result:
                self.interface_classes[name].append(schema.name)
                self.interface_attrs[name] = result

    def get_interfaces(self, name):
        """returns all the interfaces that the level called name fulfills"""
        result = []
        for k, v in self.interface_classes.items():
            print(name, k, v, (name in v), file=sys.stderr)
            if name in v:
                result.append(k)
        print(result, file=sys.stderr)
        return result

    def common_interface(self, names):
        if names[0] == 'word':
            cands = self.t_schema.interfaces
        else:
            cands = self.schema_by_name(names[0]).interfaces
        for name in names[1:]:
            cands.intersection_update(self.schema_by_name(name).interfaces)
        if cands:
            return sorted(cands)[0]
        else:
            return None

    def get_obj_id(self, obj):
        if hasattr(obj, 'xml_id'):
            return obj.xml_id
        else:
            mlevel = self.mlevel_for_class(type(obj))
            if mlevel is not None:
                n = mlevel.name
            else:
                n = 'x'
            k = '%s_%s' % (n, id(obj))
            obj.xml_id = k
            self.object_by_id[k] = obj
            return k

    def add_terminal(self, w_obj):
        val = self.word_ids[self.get_obj_id(w_obj)]
        assert val == len(self.words), (val, w_obj.xml_id,
                                        len(self.words), self.words[val - 2:val + 2], self.words[-2:])
        self.words.append(getattr(w_obj, self.word_attr))
        self.w_objs.append(w_obj)

    def replace_terminal(self, posn, w_obj):
        w_obj.xml_id = self.word_ids.get_sym(posn)
        assert self.words[posn] == getattr(
            w_obj, self.word_attr), (self.words[posn], getattr(w_obj, self.word_attr))
        self.w_objs[posn] = w_obj
        self.object_by_id[w_obj.xml_id] = w_obj

    def mlevel_for_class(self, cls):
        try:
            return self.schema_by_class[cls]
        except KeyError:
            for k in cls.__bases__:
                result = self.mlevel_for_class(k)
                if result is not None:
                    return result
        return None

    def reorder_updown(self, objs):
        # 1. extract up/down graph
        # TODO: add precedence for "locality"-type things
        edges = []
        objs_dict = {}
        result = []
        objs_by_level = {}
        edges_len = 0
        for (ml, obj) in objs:
            objs_by_level[ml.name] = self.get_obj_id(obj)
        for (ml, obj) in objs:
            obj_id = self.get_obj_id(obj)
            ml.get_updown(obj, self, edges)
            objs_dict[obj_id] = (ml, obj)
            if ml.locality in objs_by_level:
                edges.append((objs_by_level[ml.locality], obj_id))
        # 2. topological sort (of keys)
        for k in topsort(edges):
            if k in objs_dict:
                result.append(objs_dict[k])
                del objs_dict[k]
        result += objs_dict.values()
        return result

    def register_object(self, obj, schema=None):
        if schema is None:
            mlevel = self.mlevel_for_class(type(obj))
        else:
            mlevel = schema
        if mlevel is None:
            print(self.schema_by_class, file=sys.stderr)
            raise ValueError("No markable level for %s (type %s)" %
                             (obj, type(obj)))
        self.markables_by_start[obj.span[0]].append((mlevel, obj))

    def make_span(self, span):
        wids = self.word_ids
        parts = []
        for start, end in zip(span[::2], span[1::2]):
            if end == start + 1:
                parts.append(wids.get_sym(start))
            else:
                parts.append('%s..%s' % (wids.get_sym(start),
                                         wids.get_sym(end - 1)))
        return ','.join(parts)

    def get_objects_by_class(self, cls, start=0, end=None):
        if end is None:
            end = len(self.words)
        objs_by_start = self.markables_by_start
        result = []
        for i in xrange(start, end):
            for (mlevel, obj) in objs_by_start[i]:
                if isinstance(obj, cls):
                    result.append(obj)
        return result

    def clear_objects_by_level(self, levelname, start=0, end=None):
        if end is None:
            end = len(self.words)
        objs_by_start = self.markables_by_start
        for i in xrange(start, end):
            objs_new = []
            for (mlevel, obj) in objs_by_start[i]:
                if mlevel.name == levelname:
                    if hasattr(obj, 'xml_id'):
                        del self.object_by_id[obj.xml_id]
                else:
                    objs_new.append((mlevel, obj))
            objs_by_start[i] = objs_new

    def write_inline_xml(self, f, start=0, end=None,
                         encoding=None):
        """inline XML serialization for part or whole of the document"""
        objs_by_start = self.markables_by_start
        if end is None:
            end = len(self.words)
        stack = []
        for i, n in izip(xrange(start, end), islice(self.w_objs, start, end)):
            # close all tags that must be closed here
            while stack and i == stack[-1][1]:
                f.write(' ' * (len(stack) - 1))
                f.write('</%s>\n' % (stack[-1][0],))
                stack.pop()
            assert (not stack or stack[-1][1] > i), (i, stack)
            # find all markables starting here
            o_here = objs_by_start[i]
            o_here.sort(key=lambda mlevel_obj: -mlevel_obj[1].span[-1])
            j = 0
            last_o = len(o_here) - 1
            m_here = []
            while j < last_o:
                end_here = o_here[j][1].span[-1]
                if end_here == o_here[j + 1][1].span[-1]:
                    # perform sort by endpoint and topological
                    # sort for coextensive up/down relationships
                    j1 = j + 1
                    while j1 <= last_o and end_here == o_here[j1][1].span[-1]:
                        j1 += 1
                    for mlevel, obj in self.reorder_updown(o_here[j:j1]):
                        m_here.append(mlevel.serialize_object(obj, self))
                    j = j1
                else:
                    mlevel, obj = o_here[j]
                    m_here.append(mlevel.serialize_object(obj, self))
                    j += 1
            while j < len(o_here):
                (mlevel, obj) = o_here[j]
                m_here.append(mlevel.serialize_object(obj, self))
                j += 1
            for m in m_here:
                need_span = False
                endpoint = m[0][-1]
                if len(m[0]) > 2:
                    need_span = True
                    if stack and m[0][-1] > stack[-1][1]:
                        endpoint = stack[-1][1]
                elif stack and m[0][-1] > stack[-1][1]:
                    need_span = True
                    endpoint = stack[-1][1]
                if need_span:
                    m[2]['span'] = self.make_span(m[0])
                open_tag(f, m[1], m[2].items(), len(stack),
                         encoding=encoding)
                f.write('>\n')
                for e in m[3]:
                    open_tag(f, e[0], e[1].items(), len(stack) + 1,
                             encoding=encoding)
                    f.write('/>\n')
                stack.append((m[1], endpoint))
            t_desc = self.t_schema.serialize_terminal(n, self)
            open_tag(f, t_desc[0], t_desc[1].items(), len(stack),
                     encoding=encoding)
            if t_desc[2]:
                f.write('>\n')
                for e in t_desc[2]:
                    open_tag(f, e[0], e[1].items(), len(stack) + 1,
                             encoding=encoding)
                    f.write('/>\n')
                f.write(' ' * (len(stack)))
                f.write('</%s>\n' % (t_desc[0],))
            else:
                f.write('/>\n')
        # finally, close everything else
        while stack:
            x = stack.pop()
            f.write(' ' * (len(stack) - 1))
            f.write('</%s>\n' % (x[0],))

    def save(self, fname):
        encoding = 'UTF-8'
        with open(fname, 'wb') as f_out:
            print('<?xml version="1.0" encoding="%s"?>' %
                  (encoding,), file=f_out)
            print('<exml-doc>', file=f_out)
            self.describe_schema(f_out, encoding=encoding)
            print('<body serialization="inline">', file=f_out)
            self.write_inline_xml(f_out)
            print('</body>', file=f_out)
            print('</exml-doc>', file=f_out)

    def json_chunk(self, start=0, end=None):
        """
        turns part or whole of the document
        into a JSON fragment
        """
        objs_by_start = self.markables_by_start
        result_by_level = {'_start': start}
        if end is None:
            end = len(self.words)
        terminals = []
        for i in xrange(start, end):
            w_obj = self.w_objs[i]
            terminals.append(self.t_schema.make_json(w_obj, self))
        result_by_level['word'] = terminals
        for i, n in izip(xrange(start, end), islice(self.w_objs, start, end)):
            # find all markables starting here
            o_here = objs_by_start[i]
            for mlevel, obj in o_here:
                m_levelname = mlevel.name
                m_objs = result_by_level.get(m_levelname)
                if m_objs is None:
                    m_objs = []
                    result_by_level[m_levelname] = m_objs
                m_objs.append(mlevel.make_json(obj, self))
        return result_by_level

    def json_insert(self, json_obj):
        """
        takes the information from a JSON
        fragment and inserts terminals and
        markables into the document
        """
        start = json_obj.get('_start', 0)
        terminals = json_obj['word']
        end = start + len(terminals)
        if start == len(self.words):
            self.w_objs += [self.t_schema.create_from_json(n, self)
                            for n in terminals]
            self.words += [
                w_obj.word for w_obj in self.w_objs[len(self.words):]]
        else:
            assert end <= len(self.words)
            assert self.words[start:end] == [n['form'] for n in terminals]
            self.w_objs[start:end] = [
                self.t_schema.create_from_json(n, self) for n in terminals]
        for i, n in izip(xrange(start, end), islice(self.w_objs, start, end)):
            n.span = [i, i + 1]
            word_id = self.get_obj_id(n)
            assert self.word_ids[word_id] == i
        markables_by_level = {}
        for schema in self.schemas:
            if schema.name not in json_obj:
                continue
            objs = json_obj[schema.name]
            markables = [schema.create_from_json(obj, self) for obj in objs]
            markables_by_level[schema.name] = markables
            for m in markables:
                self.object_by_id[self.get_obj_id(m)] = m
                self.register_object(m)
        for i, n, obj in izip(xrange(start, end), islice(self.w_objs, start, end), terminals):
            self.t_schema.fill_from_json(n, obj, self)
        for schema in self.schemas:
            if schema.name not in json_obj:
                continue
            objs = json_obj[schema.name]
            for obj, n in izip(json_obj[schema.name], markables_by_level[schema.name]):
                schema.fill_from_json(n, obj, self)

    def clear_markables(self, start=0, end=None):
        if end is None:
            end = len(self.words)
        mbs = self.markables_by_start
        for i in xrange(start, end):
            if i in mbs:
                del mbs[i]
            self.w_objs[i] = None

    def describe_schema(self, f, encoding=None):
        edge_descrs = {}
        f.write("<schema>\n")
        self.t_schema.describe_schema(f, edge_descrs, encoding=encoding)
        for schema in self.schemas:
            schema.describe_schema(f, edge_descrs, encoding=encoding)
        for (name, (schema, parents)) in edge_descrs.items():
            open_tag(f, "edge",
                     [('name', name), ('parent', '|'.join(parents))],
                     encoding=encoding)
            f.write('>\n')
            for att in schema.attributes:
                att.describe_schema(f, encoding=encoding)
            f.write('</edge>\n')
        f.write("</schema>\n")


def assign_node_ids(n, prefix, sent_start=0):
    n.span = [n.start + sent_start, n.end + sent_start]
    if hasattr(n, 'xml_id'):
        pass
    elif hasattr(n, 'id'):
        n.xml_id = '%s_%s' % (prefix, n.id)
    for n1 in n.children:
        assign_node_ids(n1, prefix, sent_start)


class GenericMarkable(object):

    def __init__(self, **kw):
        self.__dict__.update(kw)


class Text(object):

    def __init__(self, origin, doc_no=0):
        self.origin = origin
        self.doc_no = doc_no


class NamedEntity(object):

    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)


rel_map = {
    'evaluative': 'antithesis',
    'epistemic_cause': 'evidence'
}


def get_rel(info, which):
    k = getattr(info, which, None)
    if k in rel_map:
        k = rel_map[k]
    if k == 'NULL':
        k = None
    return k


def make_syntax_doc(want_ne=True, want_wsd=False,
                    want_deps=False):
    """
    Creates a :py:class:`Document` object with a TeuBa-D/Z compatible
    markable scheme.
    """
    text_schema = MarkableSchema('text', Text)
    text_schema.attributes = [TextAttribute('origin')]
    text_schema.init_attrs = text_schema.attributes
    s_schema = MarkableSchema('sentence', tree.Tree)
    s_schema.locality = 'text'
    nt_schema = MarkableSchema('node', tree.NontermNode)
    nt_schema.locality = 'sentence'
    secedge_edge = SecondaryEdges('secEdge')
    relation_edge = ReferenceEdges('relation')
    split_edge = SplitRefEdges('splitRelation')
    nt_schema.attributes = [EnumAttribute('cat'),
                            EnumAttribute('func', prop_name='edge_label'),
                            RefAttribute('parent', restriction='up',
                                         restrict_target=['node']),
                            TextAttribute('comment')]
    nt_schema.init_attrs = nt_schema.attributes[:1]
    nt_schema.edges = [secedge_edge,
                       relation_edge,
                       split_edge]
    ne_schema = MarkableSchema('ne', NamedEntity)
    ne_schema.locality = 'sentence'
    ne_schema.attributes = [EnumAttribute('type', prop_name='kind')]
    ne_schema.attributes[0].add_item('PER', u'Person')
    ne_schema.attributes[0].add_item('ORG', u'Organisation')
    ne_schema.attributes[0].add_item('GPE', u'Gebietskörperschaft')
    ne_schema.attributes[0].add_item('LOC', u'Ort')
    ne_schema.attributes[0].add_item('OTH', u'andere Eigennamen')
    ne_schema.init_attrs = ne_schema.attributes
    t_schema = TerminalSchema('word', tree.TerminalNode)
    t_schema.attributes = [TextAttribute('form', prop_name='word'),
                           EnumAttribute('pos', prop_name='cat'),
                           EnumAttribute('morph', default_val='--'),
                           TextAttribute('lemma', default_val='--'),
                           EnumAttribute('func', prop_name='edge_label'),
                           RefAttribute('parent', restriction='up',
                                        restrict_target=['node']),
                           TextAttribute('comment')]
    t_schema.edges = [secedge_edge,
                      relation_edge,
                      split_edge]
    all_schemas = [s_schema, nt_schema, text_schema]
    if want_ne:
        all_schemas.append(ne_schema)
    if want_wsd:
        t_schema.attributes[-1:-1] = [TextAttribute(
            'wsd-lexunits', prop_name='wsd_lexunits'),
            TextAttribute('wsd-comment', prop_name='wsd_comment')]
    if want_deps:
        t_schema.attributes[-1:-1] = [RefAttribute(
            'dephead', prop_name='syn_parent', restrict_target=['word']),
            EnumAttribute('deprel', prop_name='syn_label')]
    return Document(t_schema, all_schemas)


def make_noderef(x):
    sentid, nodeid = x.split(':')
    try:
        nid = int(nodeid)
    except ValueError:
        return 's%s_%s' % (sentid, nodeid)
    else:
        if nid < 500:
            nid += 1
        return 's%s_%d' % (sentid, nid)


def make_parts(xs, offset=0):
    spans = []
    current = None
    for x in xs:
        if current:
            if current[1] == x:
                current[1] = x + 1
            else:
                spans.append(current[0] + offset)
                spans.append(current[1] + offset)
                current = [x, x + 1]
        else:
            current = [x, x + 1]
    if current:
        spans.append(current[0] + offset)
        spans.append(current[1] + offset)
    return spans


def add_tree_to_doc(t, ctx, start=None):
    """
    adds a :py:class:`pytree.tree.Tree` instance
    to the document, extending terminals and the
    node and sentence markable levels
    """
    if start is None:
        sent_start = len(ctx.words)
    else:
        sent_start = start
    if hasattr(t, 'sent_no'):
        prefix = 's%s' % (t.sent_no,)
        t.xml_id = prefix
    elif hasattr(t, 'xml_id'):
        prefix = t.xml_id
    else:
        assert False, t
    for i, n in enumerate(t.terminals):
        n.xml_id = '%s_%d' % (prefix, i + 1)
    for n in t.roots:
        assign_node_ids(n, prefix, sent_start)
    if hasattr(t, 'all_nes'):
        last_num = defaultdict(int)
        suffixes = ['', 'a', 'b', 'c', 'd']
        for kind, local_span in t.all_nes:
            ne = NamedEntity(kind)
            assert local_span, ('Empty NE span in sentence %s' % (t.sent_no,))
            ne.span = [k + sent_start for k in local_span]
            ne_start = ne.span[0]
            suff = suffixes[last_num[ne_start]]
            last_num[ne_start] += 1
            ne.xml_id = 'ne_%s%s' % (ne_start, suff)
            ctx.register_object(ne)
    if start is None:
        for n in t.terminals:
            ctx.add_terminal(n)
    else:
        for i, n in enumerate(t.terminals):
            ctx.replace_terminal(start + i, n)
    t.span = [sent_start, sent_start + len(t.terminals)]
    ctx.register_object(t)
    for n in t.node_table.values():
        ctx.register_object(n)


def postprocess_doc(doc, start=0, end=None):
    for t in doc.get_objects_by_class(tree.Tree, start, end):
        t.terminals = doc.w_objs[t.span[0]:t.span[-1]]
        all_nonterm = doc.get_objects_by_class(
            tree.NontermNode, t.span[0], t.span[-1])
        for n in all_nonterm:
            n.children = []
            n.start = n.span[0] - t.span[0]
            n.end = n.span[-1] - t.span[0]
        roots = []
        for i, n in enumerate(t.terminals):
            if n.parent is not None:
                n.parent.children.append(n)
            else:
                roots.append(n)
            n.start = i
            n.end = i + 1
        for n in all_nonterm:
            if n.parent is not None:
                n.parent.children.append(n)
            else:
                roots.append(n)
        roots.sort(key=lambda n: n.span[0])
        t.roots = roots
        for n in all_nonterm:
            assert n.children, (n.span, n.cat, n.xml_id, t.span, t.xml_id)
            n.children.sort(key=lambda n1: n1.span[0])


def read_json_doc(f_in, make_schema=None):
    """
    reads a JSON file with a single document
    according to the syntax_doc(TüBa-D/Z) schema
    """
    if make_schema is None:
        make_schema = make_syntax_doc
    doc = make_schema()
    json_obj = json.load(f_in)
    doc.json_insert(json_obj)
    postprocess_doc(doc)
    return doc


class XMLCorpusReader(object):
    """
    Code to read an EXML corpus in XML form.
    This is currently considered experimental.
    """

    def __init__(self, doc, fname, encoding='UTF-8'):
        self.doc = doc
        self.fname = fname
        self.parse = etree.iterparse(open(fname, 'rb'), events=('start', 'end',))
        self.state = 'BEFORE_HEAD'
        self.encoding = encoding
        self.markable_stack = []
        self.old_posn = 0

    def read_header(self):
        # read until end of header
        if self.state != 'BEFORE_HEAD':
            assert False
        while True:
            evt, elem = next(self.parse)
            if evt == 'end' and elem.tag == 'schema':
                process_schema(self.doc, elem)
                self.state = 'BEFORE_BODY'
                return

    def addNext(self):
        print("addNext called", file=sys.stderr)
        # read until end-of-text or end-of-body and return last_stop
        if self.state in ['BEFORE_HEAD']:
            self.read_header()
        doc = self.doc
        markable_stack = self.markable_stack
        encoding = self.encoding
        last_stop = len(doc.words)
        cur_pos = last_stop
        while self.state == 'BEFORE_BODY':
            evt, elem = next(self.parse)
            if evt == 'start' and elem.tag == 'body':
                self.state = 'IN_BODY'
        if self.state == 'AT_END':
            raise StopIteration()
        while True:
            try:
                evt, elem = next(self.parse)
            except StopIteration:
                self.state = 'AT_END'
                return len(doc.words)
            if evt == 'end' and elem.tag == 'body':
                # wrap up any loose ends
                for chld in elem.getchildren():
                    fill_attributes(chld, doc, encoding)
                if last_stop != self.old_posn:
                    self.old_posn = last_stop
                    return last_stop
            elif evt == 'start':
                # create markable
                # if a markable or word does not have an XML-id,
                # assign one by default
                if elem.tag == 'word':
                    schema = doc.t_schema
                    obj = schema.create_from_xml(elem, doc, encoding)
                    obj.span = [cur_pos, None]
                    #print >>sys.stderr, "found word: %s"%(obj.word,)
                    doc.add_terminal(obj)
                    doc.object_by_id[obj.xml_id] = obj
                    in_word = True
                else:
                    # set start point
                    try:
                        schema = doc.schema_by_name(elem.tag)
                    except KeyError:
                        # assume it's an edge; we'll deal with it later
                        if in_word:
                            (schema, obj) = (doc.t_schema, doc.words[-1])
                        elif markable_stack:
                            (schema, obj) = markable_stack[-1]
                        else:
                            schema = obj = None
                        try:
                            edge_schema = schema.edge_by_name(elem.tag)
                        except KeyError:
                            edge_schema = None
                        if edge_schema is not None:
                            print("edge: %s" % (elem.tag), file=sys.stderr)
                        else:
                            print("No schema:", elem.tag, [
                                  s.name for s in doc.schemas])
                    else:
                        obj = schema.create_from_xml(elem, doc, encoding)
                        obj.span = [cur_pos, None]
                        markable_stack.append((schema, obj))
            elif evt == 'end':
                # print elem.tag, markable_stack
                if elem.tag == 'word':
                    in_word = False
                    cur_pos += 1
                elif elem.tag == 'body':
                    for chld in elem.getchildren():
                        fill_attributes(chld, doc, encoding)
                    elem.clear()
                    # TODO wrap up stuff
                    self.old_posn = doc.size()
                    return doc.size()
                elif markable_stack and elem.tag == markable_stack[-1][0].name:
                    # set end point of markable
                    (schema, obj) = markable_stack.pop()
                    obj.span[1] = cur_pos
                    doc.register_object(obj, schema)
                if elem.tag in ['text', 'doc']:
                    fill_attributes(elem, doc, encoding)
                    elem.clear()
                    self.old_posn = last_stop
                    return last_stop


class JSONCorpusReader:

    def __init__(self, doc, fname):
        self.doc = doc
        self.fname = fname
        self.f = file(fname)

    def addNext(self):
        # TODO: basic consistency check to ensure
        # that JSON offsets are right
        l = self.f.readline()
        if l == '':
            raise StopIteration
        last_stop = len(self.doc.words)
        obj = json.loads(l)
        self.doc.json_insert(obj)
        return last_stop


def read_trees_exml(fname):
    """
    reads in an EXML file and returns a sequence of trees,
    similar to read_trees() does for treebank files
    """
    # TODO add a parameter for reading in JSON-format EXML files?
    doc = make_syntax_doc(want_deps=True)
    reader = XMLCorpusReader(doc, fname)
    last_stop = len(doc.words)
    while True:
        try:
            new_stop = reader.addNext()
            print("last_stop=%d new_stop=%d" % (
                last_stop, new_stop), file=sys.stderr)
            if new_stop != last_stop:
                trees = doc.get_objects_by_class(
                    tree.Tree, last_stop, new_stop)
                print("%d sentences in %d tokens" % (
                    len(trees), new_stop - last_stop), file=sys.stderr)
                for t in trees:
                    # TODO fill terminals
                    t.terminals = doc.w_objs[t.span[0]:t.span[-1]]
                    for i, n in enumerate(t.terminals):
                        n.start = i
                        n.end = i + 1
                    # TODO fill roots
                    # TODO set start/end of NT nodes
                    yield t
                last_stop = new_stop
        except StopIteration:
            trees = doc.get_objects_by_class(
                tree.Tree, last_stop, len(doc.words))
            assert len(trees) == 0
            break


def load(fname):
    """
    reads an EXML document as produced by ExmlPipe

    :param fname: the filename of the EXML document 
    :return: an exmldoc.Document
    """
    doc = make_syntax_doc(want_deps=True)
    reader = XMLCorpusReader(doc, fname)
    last_stop = len(doc.words)
    while True:
        try:
            reader.addNext()
        except StopIteration:
            postprocess_doc(doc)
            return doc


def write_corpus_xml(doc, reader, f_out, encoding="ISO-8859-15"):
    """
    writes a corpus as an ExportXMLv2 xml file
    """
    print('<?xml version="1.0" encoding="%s"?>' % (encoding,), file=f_out)
    print('<exml-doc>', file=f_out)
    doc.describe_schema(f_out)
    # do the actual conversion
    print('<body serialization="inline">', file=f_out)
    last_stop = len(doc.words)
    while True:
        try:
            new_stop = reader.addNext()
            if (new_stop != last_stop):
                doc.write_inline_xml(f_out, last_stop, new_stop)
                doc.clear_markables(last_stop, new_stop)
                last_stop = new_stop
        except StopIteration:
            break
    doc.write_inline_xml(f_out, last_stop)
    print('</body>', file=f_out)
    print('</exml-doc>', file=f_out)


def write_corpus_json(doc, reader, f_out):
    """
    writes a corpus as one JSON expression per document
    """
    last_stop = len(doc.words)
    while True:
        try:
            new_stop = reader.addNext()
            if (new_stop != last_stop):
                print(json.dumps(doc.json_chunk(last_stop, new_stop)), file=f_out)
                doc.clear_markables(last_stop, new_stop)
                last_stop = new_stop
        except StopIteration:
            break
    print(json.dumps(doc.json_chunk(last_stop)), file=f_out)


def process_node_schema(doc, schema, elem):
    """
    processes the part regarding one markable in the EXML document
    schema
    """
    for chld in elem.getchildren():
        if chld.tag == 'text-attr':
            tag_name = chld.attrib['name']
            try:
                att = schema.attribute_by_name(tag_name)
            except KeyError:
                print("Undeclared text attribute: %s.%s" % (
                    schema.name, tag_name,), file=sys.stderr)
                att = TextAttribute(tag_name, '_auto_%s' % (tag_name,))
                schema.add_attribute(att)
        elif chld.tag == 'enum-attr':
            tag_name = chld.attrib['name']
            try:
                att = schema.attribute_by_name(tag_name)
            except KeyError:
                print("Undeclared enum attribute: %s.%s" % (
                    schema.name, tag_name,), file=sys.stderr)
                att = EnumAttribute(tag_name,
                                    prop_name='_auto_%s' % (tag_name,))
                schema.add_attribute(att)
            for elm_val in chld.findall('val'):
                # TODO check what happens with double attributes
                att.add_item(elm_val.attrib['name'],
                             elm_val.attrib.get('description', None))
        elif chld.tag == 'node-ref':
            tag_name = chld.attrib['name']
            try:
                att = schema.attribute_by_name(tag_name)
            except KeyError:
                print("Undeclared node reference: %s.%s" % (
                    schema.name, tag_name,), file=sys.stderr)
                att = RefAttribute(tag_name,
                                   prop_name='_auto_%s' % (tag_name,))
                schema.add_attribute(att)
        else:
            print('Unkown tag in node schema: %s' %
                  (chld.tag,), file=sys.stderr)


def process_schema(doc, elem):
    """given an EXML document doc and a XML element elem
    with the attributes, add stuff to the schema
    """
    for chld in elem.getchildren():
        if chld.tag == 'tnode':
            node_name = chld.attrib['name']
            assert node_name == 'word'
            process_node_schema(doc, doc.t_schema, chld)
        elif chld.tag == 'node':
            node_name = chld.attrib['name']
            try:
                schema = doc.schema_by_name(node_name)
            except KeyError:
                print("Undeclared markable level: %s" %
                      (node_name,), file=sys.stderr)
                # TODO add locality information
                cls = type('auto_markable_%s' % (node_name,),
                           (GenericMarkable,), {})
                schema = MarkableSchema(node_name, cls)
                doc.add_schemas([schema])
            process_node_schema(doc, schema, chld)
        elif chld.tag == 'edge':
            edge_name = chld.attrib['name']
            node_names = chld.attrib['parent'].split('|')
            for node_name in node_names:
                if node_name == 'word':
                    schema = doc.t_schema
                else:
                    schema = doc.schema_by_name(node_name)
                try:
                    edge_schema = schema.edge_by_name(edge_name)
                except KeyError:
                    # TODO add to markable level
                    print("Undeclared edge schema: %s.%s" % (
                        node_name, edge_name), file=sys.stderr)
                    edge_schema = GenericEdges(edge_name,
                                               prop_name='auto_%s' % (edge_name,))
                    schema.add_edge(edge_schema)
                process_node_schema(doc, edge_schema, chld)


def fill_attributes(elem, doc, encoding=None):
    try:
        xml_id = elem.attrib[QNAME_XML_ID]
    except KeyError:
        print("No ID: %s" % (elem,), file=sys.stderr)
        return
    obj = doc.object_by_id[xml_id]
    if elem.tag == 'word':
        schema = doc.t_schema
    else:
        schema = doc.schema_by_name(elem.tag)
    schema.fill_from_xml(obj, elem, doc, encoding)
    for chld in elem.getchildren():
        if chld.tag == 'word':
            fill_attributes(chld, doc, encoding)
        else:
            try:
                c_schema = doc.schema_by_name(chld.tag)
            except KeyError:
                e_schema = schema.edge_by_name(chld.tag)
                edges = e_schema.get_edges(obj, doc)
                val = []
                for att in e_schema.attributes:
                    if att.name in chld.attrib:
                        val.append(att.unmap_attr(chld.attrib[att.name],
                                                  doc, encoding))
                    else:
                        print("No val for %s.%s.%s" % (
                            schema.name, e_schema.name, att.name))
                        val.append(None)
                # print e_schema.name, val
                edges.append(val)
                e_schema.set_edges(obj, edges, doc)
                continue
            else:
                fill_attributes(chld, doc, encoding)
