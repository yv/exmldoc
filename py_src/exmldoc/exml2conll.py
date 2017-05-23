#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
'''
Creates a CQP-style column output from a EXML file.

Usage:
export2cqp [-f format] [-o output.txt] inputfile.exml.xml
'''
from __future__ import print_function

import sys
import os.path
import getopt
import glob

import exml


class ExportToCoNLL:
    """
    writes CoNLL-U (
    """

    def __init__(self, format='conllu', opts=None):
        self.format = format

        self.p_atts = []

    def write_conll(self, fname, f_out=None):
        if f_out is None:
            f_out = sys.stdout
        count = 0
        if self.format == 'conllu':
            print("# document: %s"%(fname,), file=f_out)
        for t in exml.read_trees_exml(fname):
            if self.format == 'conllu':
                if hasattr(t, 'sent_no'):
                    print("# sentence id: %s" % (t.sent_no,), file=f_out)
                elif hasattr(t, 'xml_id'):
                    print("# sentence id: %s" % (t.xml_id,), file=f_out)
                print("# sentence-text: %s"%(' '.join([n.word for n in t.terminals])))
            count += len(t.terminals)
            sent_start = t.terminals[0].span[0]
            for i, n in enumerate(t.terminals):
                print("%d\t%s\t%s\t%s\t%s" % (
                    i+1,
                    n.word, n.cat, n.lemma, n.morph), file=f_out)
            if self.want_deprels:
                for n in t.terminals:
                    lbl = getattr(n, 'syn_label', None)
                    if not hasattr(n, 'syn_parent') or n.syn_parent is None:
                        attach = 'ROOT'
                        lbl = 'ROOT'
                    else:
                        attach = '%+d' % (n.syn_parent.start - n.start)
                    if not hasattr(n, 'lemma') or n.lemma is None:
                        lemma = '_'
                    else:
                        lemma = n.lemma
                    print("%s\t%s\t%s\t%s\t%s\t%s" % (
                        n.word, n.cat, lemma, n.morph, lbl, attach), file=f_out)
            else:
                for n in t.terminals:
                    print("%s\t%s\t%s\t%s" % (
                        n.word, n.cat, n.lemma, n.morph), file=f_out)
            print("</s>", file=f_out)
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
            f_out = file(v, 'w')
    app = ExportToCoNLL(opts)
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
            for l in open(offsets_fname, 'rb'):
                line = l.strip().split()
                fname = fname0 = line[0]
                if not fname.endswith('.exml.xml'):
                    fname = fname + '.exml.xml'
                f_path = os.path.join(args[0], fname)
                all_files.remove(f_path)
                print("<doc id=%s>" % (fname0,), file=f_out)
                count_file = app.write_conll(f_path, f_out)
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
            f_offsets = open(offsets_fname, 'wb')
            count_total = 0
            for f_path in all_exml_fnames:
                fname0 = os.path.basename(f_path)
                if fname0.endswith('.exml.xml'):
                    fname0 = fname0[:-9]
                print("<doc id=%s>" % (fname0,), file=f_out)
                count_file = app.write_conll(f_path, f_out)
                print("</doc>", file=f_out)
                print("%s\t%d" % (
                    fname0, count_total), file=f_offsets)
                count_total += count_file
    else:
        app.write_conll(args[0], f_out)

if __name__ == '__main__':
    main()
