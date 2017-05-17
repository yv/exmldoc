from __future__ import print_function
import optparse
import xml.etree.cElementTree as etree
from exmldoc import make_syntax_doc, process_schema, fill_attributes


def exml_lint_main(argv=None):
    """
    Reads an EXML file and writes it back in normal form,
    allowing a conversion between ExportXML and EXML-JSON
    
    This file also demonstrates the use of exmldoc to stream
    a larger document
    """
    encoding = 'UTF-8'
    oparse = optparse.OptionParser()
    opts, args = oparse.parse_args(argv)
    ctx = etree.iterparse(args[0], events=('start', 'end'))
    doc = make_syntax_doc()
    f_out = open(args[1], 'wb')
    state = 'BEFORE_HEAD'
    markable_stack = []
    cur_pos = 0
    last_stop = 0
    in_word = False
    for evt, elem in ctx:
        if state == 'BEFORE_HEAD' and evt == 'end' and elem.tag == 'schema':
            process_schema(doc, elem)
            print('<?xml version="1.0" encoding="%s"?>' %
                  (encoding,), file=f_out)
            print('<exml-doc>', file=f_out)
            doc.describe_schema(f_out, encoding=encoding)
            state = 'BEFORE_BODY'
        elif state == 'BEFORE_BODY' and evt == 'start' and elem.tag == 'body':
            state = 'IN_BODY'
            print('<body serialization="inline">', file=f_out)
        elif state == 'IN_BODY':
            if evt == 'end' and elem.tag == 'body':
                # TODO wrap up all loose ends
                pass
            elif evt == 'start':
                # create markable
                # TODO if a markable or word does not have an XML-id,
                # assign one by default
                if elem.tag == 'word':
                    schema = doc.t_schema
                    obj = schema.create_from_xml(elem, doc, encoding)
                    obj.span = [cur_pos, None]
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
                            pass
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
                    fill_attributes(elem, doc, encoding)
                    elem.clear()
                    # write out part of the document
                    doc.write_inline_xml(f_out, last_stop, cur_pos)
                    doc.clear_markables(last_stop, cur_pos)
                    last_stop = cur_pos
                    state = 'AFTER_BODY'
                elif markable_stack and elem.tag == markable_stack[-1][0].name:
                    # set end point of markable
                    (schema, obj) = markable_stack.pop()
                    obj.span[1] = cur_pos
                    doc.register_object(obj, schema)
                if elem.tag == 'text':
                    # if it's a text markable, fill attributes and empty out
                    # the element
                    fill_attributes(elem, doc, encoding)
                    elem.clear()
                    # write out part of the document
                    doc.write_inline_xml(f_out, last_stop, cur_pos)
                    doc.clear_markables(last_stop, cur_pos)
                    last_stop = cur_pos
    print('</body>', file=f_out)
    print('</exml-doc>', file=f_out)


if __name__ == '__main__':
    exml_lint_main()
