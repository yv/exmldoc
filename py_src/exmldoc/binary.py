"""
Support for the msgpack-based binary format
"""
from msgpack import Unpacker, Packer
from collections import defaultdict, OrderedDict

class MsgpackReader(object):
    def __init__(self, f):
        self.f = f
        self.unpacker = Unpacker(f)

def schema_to_dict(schema):
    d = OrderedDict()
    for attr in schema.attributes:
        kind = attr.get_kind()
        if kind == 'ENUM':
            d[attr.name] = ['ENUM', list(attr.alphabet)]
        else:
            d[attr.name] = kind
    return d

def objects_to_packed(doc, objs, schema, want_span):
    names = []
    data = []
    names.append(':id')
    data.append([getattr(obj, 'xml_id', None) for obj in objs])
    if want_span:
        n = len(objs)
        span_array = [0] * (2*n)
        last_offset = 0
        for i, obj in enumerate(objs):
            span_array[i] = obj.span[0] - last_offset
            span_array[n+1] = obj.span[-1] - obj.span[0]
            last_offset = obj.span[-1]
        names.append(':span')
        data.append(span_array)
    for attr in schema.attributes:
        att_seq = []
        any_filled = False
        for obj in objs:
            val = getattr(obj, attr.prop_name, None)
            if val is not None:
                any_filled = True
                att_seq.append(attr.map_attr(val, doc))
            else:
                att_seq.append(None)
        if any_filled:
            names.append(attr.name)
            data.append(att_seq)
    return [len(objs), names, data]


class MsgpackWriter(object):
    def __init__(self, f):
        self.f = f
        self.packer = Packer()

    def pack(self, obj):
        self.f.write(self.packer.pack(obj))

    def write_document(self, doc):
        """
        Writes a complete EXML document

        :param doc Document: the document to write
        """
        packer = self.packer
        self.f.write(
            packer.pack_array_header(3) +
            packer.pack('exml1'))
        self.write_schema(doc)
        self.write_chunks(doc)

    def write_schema(self, doc):
        """
        Writes the schema part of an EXML document

        :param doc: the document to write
        :type doc Document:
        """
        d = {}
        d['word'] = schema_to_dict(doc.t_schema)
        for schema in doc.schemas:
            d[schema.name] = schema_to_dict(schema)
        self.pack(d)

    def write_chunks(self, doc):
        self.f.write(self.packer.pack_array_header(1))
        self.write_chunk(doc, 0, None)

    def write_chunk(self, doc, start, end):
        if end is None:
            end = len(doc.words)
        self.f.write(self.packer.pack_array_header(2))
        # write terminals
        self.pack(objects_to_packed(doc, doc.w_objs, doc.t_schema, False))
        self.write_markables(doc)

    def write_markables(self, doc):
        markables_by_layer = defaultdict(list)
        for posn in sorted(doc.markables_by_start):
            for (mlevel, obj) in doc.markables_by_start[posn]:
                markables_by_layer[mlevel.name].append(obj)
        ne_levels = []
        for schema in doc.schemas:
            if schema.name not in markables_by_layer:
                continue
            ne_levels.append(schema.name)
        self.f.write(self.packer.pack_map_header(len(ne_levels)))
        for schema in doc.schemas:
            if schema.name not in markables_by_layer:
                continue
            objs = markables_by_layer[schema.name]
            self.pack(schema.name)
            self.pack(objects_to_packed(doc, objs, schema, True))

if __name__ == '__main__':
    import sys
    from exmldoc import load
    doc = load(sys.argv[1])
    with open(sys.argv[2], 'wb') as f_out:
        wr = MsgpackWriter(f_out)
        wr.write_document(doc)