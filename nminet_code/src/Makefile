TOP=..

include $(TOP)/Makefile.inc

DIRS := schema

all: $(DIRS)

$(DIRS):
	$(MAKE) -C $@

clean distclean realclean:
	for dir in $(DIRS); do $(MAKE) -C $${dir} $@; done
	rm -f *.pyc *.pyo

.PHONY: all clean distclean realclean $(DIRS)
