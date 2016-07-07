#!python
#
# Copyright (c) 2014 Harmonic Corporation, all rights reserved
#
# Schema module utilities
#

import _list
import re as re_
from cStringIO import StringIO

__all__ = [
	"get_type_by_name",
	"get_object_by_name",
	"parse_string",
	"model_",
]

_Tag_pattern_ = re_.compile(r'({.*})?(.*)')
_GDSClassesMapping = {}
_classes = {}
_parsexml = None

class _Wrapper:
    def __init__(self, *args):
	for a in args:
	    setattr(self, a.__name__, a)


def _load_packages():
    global _classes, _parsexml, _GDSClassesMapping

    for name in _list.schemas:
	name = name.replace(".", "_")
	mod = __import__("%s_gen" % name, globals(), locals(), ["*"])

	objs = [mod.parseString]
	_parsexml = mod.parsexml_

	_GDSClassesMapping.update(mod.GDSClassesMapping)
	for n in mod.__all__:
	    o = getattr(mod, n)
	    objs.append(o)
	    _classes[n] = o

	globals()[name] = _Wrapper(*objs)
	__all__.append(name)

def get_object_by_name(name, **kwargs):
    klass = get_type_by_name(name)
    if klass is None:
	return None
    return klass.factory(**kwargs)

def get_type_by_name(name):
    klass = _GDSClassesMapping.get(name)
    if klass is None:
	klass = _classes.get(name)
    return klass

def _get_root_tag(node):
    tag = _Tag_pattern_.match(node.tag).groups()[-1]
    rootClass = get_type_by_name(tag)
    return tag, rootClass


def parse_string(inString, silence=True):
    doc = _parsexml(StringIO(inString))
    rootNode = doc.getroot()
    rootTag, rootClass = _get_root_tag(rootNode)
    rootObj = rootClass.factory()
    rootObj.build(rootNode)
    return rootObj, rootTag

class ModelWrapper(object):
    def __getattribute__(self, name):
	def f(**kw):
	    return get_object_by_name(name, **kw)
	return f
model_ = ModelWrapper()

def obj2xml(o):
	if o is None:
	    return o
	s = StringIO()
	o.export(s, 0)
	return s.getvalue()

def obj2str(klass, o):
	if o is None:
	    return o
	s = StringIO()
	o.exportLiteral(s, 0)
	return s.getvalue()

_load_packages()

