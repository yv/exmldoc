#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
'''
Creates a CQP-style column output from a EXML file.

Usage:
export2cqp [-P att] [-S satt] [-o output.txt] inputfile.exml.xml
'''
from __future__ import print_function

import sys
import os.path
import getopt
import glob

import exmldoc

if sys.version_info[0] >= 3:
    xrange = range

class ExportToCQP:

    def __init__(self, opts=None):
        self.p_atts = []
        self.s_atts = []
        if opts is None:
            self.want_deprels = False
        else:
            # add p_atts and s_atts etc.
            for k, v in opts:
                if k == '-S':
                    self.s_atts.append(v)
                elif k == '-P':
                    self.p_atts.append(v)
            self.want_deprels = False

    def write_cqp(self, reader, f_out=None):
        if f_out is None:
            f_out = sys.stdout
        count = 0
        level_map = {
            'sentence': ('s', None)
        }
        for s_att in self.s_atts:
            level_map[s_att] = (s_att, None)
        for ev in reader.inline_events(level_map):
            if ev[0] == 'start':
                # start S-attribute
                tag = ev[1]
                mapped_tag, write_fn = level_map[tag]
                attrs = ev[2]
                parts = []
                if write_fn is not None:
                    write_fn(tag, attrs)
                else:
                    for k,v in attrs:
                        if k == 'xml:id':
                            k = 'id'
                            # try to spot auto-generated IDs
                            if (v[0] == 'm' and len(v) == 7 or
                                    v.startswith('__tmp_')):
                                continue
                        parts.append(' %s=%s'%(k, v))
                    print('<%s%s>'%(mapped_tag, ''.join(parts)), file=f_out)
            elif ev[0] == 'end':
                # end S-attribute
                tag = ev[1]
                mapped_tag, write_fn = level_map[tag]
                print('</%s>'%(mapped_tag), file=f_out)
            elif ev[0] == 'terminal':
                n = ev[1]
                if not hasattr(n, 'lemma') or n.lemma is None:
                    lemma = '_'
                else:
                    lemma = n.lemma
                columns = [n.word, n.cat, lemma, n.morph]
                if self.want_deprels:
                    lbl = getattr(n, 'syn_label', '_')
                    if not hasattr(n, 'syn_parent') or n.syn_parent is None:
                        attach = 'ROOT'
                        lbl = 'ROOT'
                    else:
                        attach = '%+d'%(n.syn_parent.span[0] - n.span[0])
                    columns += [lbl, attach]
                print('\t'.join([str(x) for x in columns]), file=f_out)
                count += 1
        return count


def usage():
    print(__doc__)

def skip_through(reader):
    """
    continues reading a document until the end of the document
    :param reader: a document reader
    :param doc:    the document in question
    :return: the number of tokens in the document
    """
    last_stop = 0
    while True:
        try:
            next_stop = reader.addNext()
        except StopIteration:
            return len(reader.doc.words)


def process_directory(dirname, create_doc=None):
    """
    processes a directory of EXML files, consuming or creating an offsets.txt file
    :param dirname:
    :param create_doc:
    :return: an iterable of (fname, doc, reader) tuples
    """
    if create_doc is None:
        create_doc = lambda: exmldoc.make_syntax_doc(want_deps=True)
    offsets_fname = os.path.join(dirname, 'offsets.txt')
    all_exml_fnames = set(glob.glob(os.path.join(dirname, '*.exml.xml')))
    count_total = 0
    count_file = 0
    reader = None
    old_fname = '(START)'
    if os.path.exists(offsets_fname):
        for l in open(offsets_fname):
            line = l.strip().split()
            fname = fname0 = line[0]
            if not fname.endswith('.exml.xml'):
                fname = fname + '.exml.xml'
            if count_file is not None:
                count_total += count_file
                posn_offset = int(line[1])
                if posn_offset != count_total:
                    print("ERROR: %s at position %d, should be %d" % (
                        fname, count_total, posn_offset), file=sys.stderr)
                    print("before: %s" % (old_fname,), file=sys.stderr)
            else:
                count_total = int(line[1])
            f_path = os.path.join(dirname, fname)
            all_exml_fnames.remove(f_path)
            doc = create_doc()
            reader = exmldoc.XMLCorpusReader(doc, f_path)
            yield fname0, doc, reader
            if reader.at_end:
                count_file = len(doc.w_objs)
            else:
                count_file = None
            old_fname = fname
    if all_exml_fnames:
        if count_file is None:
            count_file = skip_through(reader)
        count_total += count_file
        with open(offsets_fname, 'a') as f_offsets:
            for fname in sorted(all_exml_fnames):
                fname0 = os.path.basename(fname)
                f_path = os.path.join(dirname, fname)
                print("%s\t%s"%(fname0, count_total), file=f_offsets)
                doc = create_doc()
                reader = exmldoc.XMLCorpusReader(doc, f_path)
                yield fname, doc, reader
                if reader.at_end:
                    count_file = len(doc.w_objs)
                else:
                    count_file = skip_through(reader)
                count_total += count_file

def main():
    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:], 'P:S:o:')
    except getopt.GetoptError:
        usage()
        sys.exit(1)
    if len(args) != 1:
        usage()
        sys.exit(1)
    f_out = None
    for k, v in opts:
        if k == '-o':
            f_out = open(v, 'w')
    app = ExportToCQP(opts)
    if os.path.isdir(args[0]):
        for fname, doc, reader in process_directory(args[0]):
            print("<doc id=%s>" % (fname,), file=f_out)
            app.write_cqp(reader, f_out)
            print("</doc>", file=f_out)
    else:
        doc = exmldoc.make_syntax_doc(want_deps=True)
        reader = exmldoc.XMLCorpusReader(doc, args[0])
        app.write_cqp(reader, f_out)


def write_cqp_entry(args=None):
    if args is None:
        args = sys.argv[1:]
    opts, args = getopt.gnu_getopt(args, 'dc:')
    env = {'cqp_dir': '/export/local/yannick/cqp',
           'want_deprels': False}
    for k, v in opts:
        if k == '-d':
            env['want_deprels'] = True
        elif k == '-c':
            env['cqp_dir'] = v
    env['corpus'] = args[0].upper()
    env['corpus_lower'] = args[0].lower()
    if env['cqp_dir'][-1] == '/':
        env['cqp_dir'] = env['cqp_dir'][:-1]
    print('''##
## registry entry for corpus %(corpus_lower)s
##

# long descriptive name for the corpus
NAME "%(corpus_lower)s"
# corpus ID (must be lowercase in registry!)
ID   %(corpus_lower)s
# path to binary data files
HOME %(cqp_dir)s/%(corpus_lower)s
# optional info file (displayed by "info;" command in CQP)
INFO %(cqp_dir)s/%(corpus_lower)s/.info

# corpus properties provide additional information about the corpus:
##:: charset  = "latin1" # change if your corpus uses different charset
##:: language = "??"     # insert ISO code for language (de, en, fr, ...)


##
## p-attributes (token annotations)
##

ATTRIBUTE word
ATTRIBUTE pos
ATTRIBUTE lemma
ATTRIBUTE morph
''' % env)
    if env['want_deprels']:
        print('''ATTRIBUTE deprel
ATTRIBUTE attach

''')
    print('''##
## s-attributes (structural markup)
##

# <s id=".."> ... </s>
# (no recursive embedding allowed)
STRUCTURE s                    # [annotations]
STRUCTURE s_id                 # [annotations]

# <text id=".."> ... </text>
# (no recursive embedding allowed)
STRUCTURE text                 # [annotations]
STRUCTURE text_id              # [annotations]
''')


if __name__ == '__main__':
    main()
