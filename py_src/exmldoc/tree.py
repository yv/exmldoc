from __future__ import print_function
import sys
import re

unwanted_mrg = re.compile(r"([^A-Za-z0-9\x80-\xff\-_])")


def escape_mrg(string):
    if not string:
        return ''
    return unwanted_mrg.sub(r"\\\1", string)


def bottomup_enumeration(nodes):
    # print "bottomup_enumeration: %s"%(nodes)
    for n in nodes:
        for n1 in bottomup_enumeration(n.children):
            yield n1
        yield n


def descendants(node):
    for n in node.children:
        yield n
        for n1 in descendants(n):
            yield n1
    return


def determine_tokenspan(node):
    if not node.isTerminal():
        if not node.children:
            raise ValueError('NT Node %s#%s has no children' % (
                node.cat, node.id))
        node.start = min(map(lambda x: x.start, node.children))
        node.end = max(map(lambda x: x.end, node.children))


class Tree(object):
    '''
    a Tree object represents a syntax tree.
    You can access roots (nodes with no parent node) and
    the leaves (preterminal nodes) through its attributes.

    .. py:attribute:: roots

       The roots of the tree.

    .. py:attribute:: terminals

       The leaves/pre-terminals of the tree

    .. py:attribute:: encoding

       The encoding for any (non-unicode) string values in the tree's nodes
    '''
    __slots__ = ['node_table', 'roots', 'terminals', 'encoding',
                 '__dict__']

    def __getstate__(self):
        return (self.node_table,
                self.roots,
                self.terminals,
                self.__dict__)

    def __setstate__(self, state):
        self.node_table, self.roots, self.terminals, self.__dict__ = state

    def __init__(self):
        self.node_table = {}
        self.roots = []
        self.terminals = []

    def __iter__(self):
        return iter(self.roots)

    def bottomup_enumeration(self):
        '''
        returns a sequence of all (nonterminal as well
        as terminal) nodes in the tree, in left-to-right,
        bottom-up order
        '''
        return bottomup_enumeration(self.roots)

    def topdown_enumeration(self):
        '''
        returns a sequence of all (nonterminal and terminal)
        nodes in the tree, in left-to-right, top-down order
        '''
        for n in self.roots:
            yield n
            for n1 in descendants(n):
                yield n1
        return

    def determine_tokenspan_all(self):
        "determines the tokenspan for all nodes and sorts children accordingly"
        def by_pos(a, b):
            return cmp(a.start, b.start)
        try:
            for node in self.bottomup_enumeration():
                determine_tokenspan(node)
                node.children.sort(by_pos)
        except:
            print("In tree: %s" %
                  (getattr(self, 'sent_no', '???'),), file=sys.stderr)
            raise
        self.roots.sort(by_pos)

    def check_roots(self):
        for n in self.roots:
            assert n.parent is None, (repr(n), getattr(self, 'sent_no', None))
            self.check_nodes(n, [])

    def check_nodes(self, node, parents):
        if node.parent is None:
            assert parents == [], (repr(node), getattr(self, 'sent_no', None))
        else:
            assert node.parent == parents[-1], (repr(node),
                                                getattr(self, 'sent_no', None))

        parents.append(node)
        for n in node.children:
            assert not n in parents
            self.check_nodes(n, parents)
        del parents[-1]

    def check_node_table(self):
        for k, n in self.node_table.iteritems():
            assert n.id == k

    def renumber_ids(self, nodes=None, start=500):
        """gives ids to all nonterminal nodes."""
        pos = start
        if nodes == None:
            # renumber all IDs and clear out node_table
            self.node_table = {}
            nodes = self.roots
        for n in nodes:
            if not n.isTerminal():
                # print "Renumber %r: entering %s, pos=%d"%(n.id,pos)
                pos = 1 + self.renumber_ids(n.children, pos)
                #sys.stderr.write("Renumber %r: %s => %d\n"%(n,n.id,pos))
                n.id = "%s" % pos
                self.node_table[n.id] = n
        return pos

    def check_nodetable(self):
        for key in self.node_table:
            if self.node_table[key].id != key:
                raise "Nodetable: node %s(%r) has id %s" % (key,
                                                            self.node_table[key], self.node_table[key].id)
            assert self.node_table[key].id == key
            if self.node_table[key].parent == None:
                assert self.node_table[key] in self.roots
            else:
                parent = self.node_table[key].parent
                assert self.node_table[parent.id] == parent

    def discontinuity(self, nodes, index, sent_node):
        """returns True iff there is a discontinuity between
        the Nth and the N+1th member of nodes, ignoring
        punctuation and parentheses."""
        if nodes[index].end == nodes[index + 1].start:
            return False
        sys.stderr.write('Looking for a discontinuity between %r and %r' % (
            self.terminals[nodes[index].end],
            self.terminals[nodes[index + 1].start]))
        for n in self.terminals[nodes[index].end:nodes[index + 1].start]:
            n1 = n
            while n1 != None:
                if n1 == sent_node:
                    return True
                n1 = n1.parent
        return False


# abstract base class for all nodes
class Node(object):

    def __init__(self, cat):
        self.id = None
        self.start = -1
        self.end = -1
        self.cat = cat
        self.children = []
        self.parent = None

    def add_at(self, node, pos):
        self.children[pos:pos] = [node]
        node.set_parent(self)

    def append(self, node):
        self.children.append(node)
        node.set_parent(self)

    def insert(self, node):
        "inserts a node at the appropriate position"
        node.set_parent(self)
        for (i, n) in enumerate(self.children):
            if (n.start >= node.start):
                self.children[i:i] = [node]
                return
        self.append(node)

    def set_parent(self, parent):
        self.parent = parent


class NontermNode(Node):
    '''
    Node class for nonterminal node

    The exact set of attributes for a nonterminal
    is use-dependent, but the core set of these consists in

    .. py:attribute:: cat

       the node category (e.g. NP)

    .. py:attribute:: edge_label

       the grammatical function/edge label of this node
       (e.g. subject, modifier)

    .. py:attribute:: children

       a list of the children of this node, sorted by starting
       position

    For many uses, the following attributes are also relevant:

    .. py:attribute:: start

       the start position (usually inferred through determine_tokenspans_all
       as the leftmost position of any terminal in its yield).

    .. py:attribute:: end

       the end position, as one more than the rightmost position of
       any terminal in its yield

    .. py:attribute:: xml_id

       the identifier that this nodes gets in any XML-based formats
       such as EXML, TigerXML or PML
    '''

    def __init__(self, cat, edge_label=None):
        Node.__init__(self, cat)
        self.edge_label = edge_label
        self.attr = '--'

    def __repr__(self):
        stuff = ''
        if hasattr(self, 'xml_id'):
            stuff += '#' + self.xml_id
        stuff += ' at ' + hex(id(self))
        return '<%s.%s%s>' % (self.cat, self.edge_label, stuff)

    def isTerminal(self):
        return False

    def __str__(self):
        return '<NonTerm %s #%s>' % (self.cat, self.id)

    def to_penn(self):
        s = self.cat
        s = s.replace('(', '-LRB-')
        s = s.replace(')', '-RRB-')
        a = "(%s " % (s,)
        a += ' '.join(map(lambda x: x.to_penn(), self.children))
        a += ")"
        return a

    def to_full(self, wanted_attrs):
        pairs = []
        for key in wanted_attrs:
            pairs.append('%s=%s' %
                         (key, escape_mrg(str(getattr(self, key, '--')))))
        a = "(%s" % (escape_mrg(self.cat))
        if pairs:
            a = a + "=#i[%s]" % (' '.join(pairs))
        a += " %s)" % (' '.join(map(lambda x: x.to_full(wanted_attrs), self.children)),
                       )
        return a


class TerminalNode(Node):

    '''
    Node class for a preterminal node.

    These usually have the following attributes:

    .. py:attribute:: word

       the surface form of the word of this terminal

    .. py:attribute:: cat

       the POS tag (syntactic category)

    .. py:attribute:: morph

       the morphological tag

    .. py:attribute:: lemma

       the lemma of this node

    .. py:attribute:: start

       the position of this node

    .. py:attribute:: xml_id

       the XML id of this node

    If this node is part of a dependency tree, it will usually also have
    the attributes:

    .. py:attribute:: syn_parent

       the governor of this word (i.e., a reference to another TerminalNode)

    .. py:attribute:: syn_label

       the dependency label of this word

    '''

    def __init__(self, cat, word, edge_label=None, morph=None):
        Node.__init__(self, cat)
        self.word = word
        self.edge_label = edge_label
        self.morph = morph

    def __repr__(self):
        if hasattr(self, 'xml_id'):
            stuff = '#' + self.xml_id
        else:
            stuff = '(%d)' % (self.start)
        return '<%s/%s%s at %s>' % (self.word, self.cat, stuff, hex(id(self)))

    def isTerminal(self):
        return True

    def to_penn(self):
        cat = self.cat
        cat = cat.replace('(', '-LRB-')
        cat = cat.replace(')', '-RRB-')
        word = self.word
        word = word.replace('(', '-LRB-')
        word = word.replace(')', '-RRB-')
        return "(%s %s)" % (self.cat, self.word)

    def to_full(self, wanted_attrs):
        pairs = []
        for key in wanted_attrs:
            pairs.append('%s=%s' %
                         (key, escape_mrg(str(getattr(self, key, '--')))))
        a = "(%s" % (escape_mrg(self.cat),)
        if pairs:
            a = a + "=#i[%s]" % (' '.join(pairs))
        a += " %s)" % (escape_mrg(self.word),)
        return a
