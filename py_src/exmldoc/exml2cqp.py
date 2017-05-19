#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
'''
Creates a CQP-style column output from a EXML file.

Usage:
export2cqp [-P att] [-S satt] [-o output.txt] inputfile.export
'''
from __future__ import print_function

import sys
import os.path
import getopt
import glob
from itertools import izip, islice

import exmldoc
from exmldoc import open_tag
from exmldoc import tree

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

    def write_cqp(self, fname, f_out=None):
        if f_out is None:
            f_out = sys.stdout
        count = 0
        level_map = {
            'sentence': ('s', None)
        }
        for s_att in self.s_atts:
            level_map[s_att] = (s_att, None)
        doc = exmldoc.make_syntax_doc(want_deps=True)
        reader = exmldoc.XMLCorpusReader(doc, fname)
        for ev in reader.inline_events(level_map):
            if ev[0] == 'start':
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
                    print('<%s%s>'%(mapped_tag, ''.join(parts)))
            elif ev[0] == 'end':
                tag = ev[1]
                mapped_tag, write_fn = level_map[tag]
                print('</%s>'%(mapped_tag))
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
                print('\t'.join([str(x) for x in columns]))
                count += 1
        return count


def usage():
    print(__doc__)


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
        # TODO do something sensible
        offsets_fname = os.path.join(args[0], 'offsets.txt')
        all_exml_fnames = glob.glob(os.path.join(args[0], '*.exml.xml'))
        if os.path.exists(offsets_fname):
            # Case 1: offsets.txt already exists
            # iterate over the files in offsets.txt, making sure
            # (i) no files are missed, (ii) the offsets still match
            all_files = set(all_exml_fnames)
            count_total = 0
            old_fname = '(START)'
            for l in file(offsets_fname):
                line = l.strip().split()
                fname = fname0 = line[0]
                if not fname.endswith('.exml.xml'):
                    fname = fname + '.exml.xml'
                f_path = os.path.join(args[0], fname)
                all_files.remove(f_path)
                print("<doc id=%s>" % (fname0,), file=f_out)
                count_file = app.write_cqp(f_path, f_out)
                print("</doc>", file=f_out)
                posn_offset = int(line[1])
                if posn_offset != count_total:
                    print("ERROR: %s at position %d, should be %d" % (
                        fname, count_total, posn_offset), file=sys.stderr)
                    print("before: %s" % (old_fname,), file=sys.stderr)
                count_total = posn_offset + count_file
                old_fname = fname
            if all_files:
                # TODO: append new files to offsets.txt?
                for fname in sorted(all_files):
                    print("ERROR: %s is missing in offsets.txt" % (
                        fname,), file=sys.stderr)
        else:
            # Case 2: create offsets.txt
            f_offsets = file(offsets_fname, 'w')
            count_total = 0
            for f_path in all_exml_fnames:
                fname0 = os.path.basename(f_path)
                if fname0.endswith('.exml.xml'):
                    fname0 = fname0[:-9]
                print("<doc id=%s>" % (fname0,), file=f_out)
                count_file = app.write_cqp(f_path, f_out)
                print("</doc>", file=f_out)
                print("%s\t%d" % (
                    fname0, count_total), file=f_offsets)
                count_total += count_file
    else:
        app.write_cqp(args[0], f_out)


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
