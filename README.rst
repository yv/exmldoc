ExmlDoc
=======

.. image:: https://travis-ci.org/yv/exmldoc.svg?branch=master
    :target: https://travis-ci.org/yv/exmldoc

exmldoc is a library for loading .exml.xml files either produced by PyTree or by the ExportXMLv2 Java library
and assorted tools. The EXML file format is one of the file formats used for the TüBa-D/Z treebank of German and
offers the possibility to store multilayer linguistic annotations in a (mostly) human-readable format.

As long as you are working with small documents, usage is relatively simple: load a document with

::
  import exmldoc
  from exmldoc.tree import Tree

  doc = exmldoc.load('file.exml.xml')


you can then (for example) enumerate all sentences with:

::
  for sent in doc.get_objects_by_class(Tree):
    print doc.words[sent.span[0]:sent.span[1]]

or access the token objects with

::
  for sent in doc.get_objects_by_class(Tree):
    for token in doc.w_objs[sent.span[0]:sent.span[1]]
        print token.word, token.cat, token.lemma

You can change a document and then save it with

::
  doc.save('file_processed.exml.xml')
