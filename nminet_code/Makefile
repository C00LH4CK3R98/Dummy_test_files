TOP=.

include $(TOP)/Makefile.inc

NMINET_DIR := /opt/omneon/nmi/nminet

DIRS := src

INST_CLEAN_RULE= -name '*.pyc' -o -name '*.pyo' -o -name '*.bak' -o -name '.*' -o -name 'Makefile*'

all: $(DIRS)

$(DIRS):
	$(MAKE) -C $@

clean distclean realclean:
	for dir in $(DIRS); do $(MAKE) -C $${dir} $@; done
	find -H $(TOP)/lib/pyroute2 -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
	find -H $(TOP)/lib/enum -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
	find -H $(TOP)/bin -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

install: all
	install -d $(INSTALL_DIR)$(NMINET_DIR)/bin
	install -d $(INSTALL_DIR)$(NMINET_DIR)/lib
	install -d $(INSTALL_DIR)$(NMINET_DIR)/src
	install -d $(INSTALL_DIR)$(NMINET_DIR)/src/schema

	install -m 0755 $(TOP)/bin/nminet $(INSTALL_DIR)$(NMINET_DIR)/bin
	install -m 0755 $(TOP)/bin/nminetctl.py $(INSTALL_DIR)$(NMINET_DIR)/bin
	install -m 0755 $(TOP)/bin/nminet_check $(INSTALL_DIR)$(NMINET_DIR)/bin
	cp -r $(TOP)/lib/* $(INSTALL_DIR)$(NMINET_DIR)/lib/
	cp -r $(TOP)/src/* $(INSTALL_DIR)$(NMINET_DIR)/src/
	find -H $(INSTALL_DIR)$(NMINET_DIR)/lib/ -type f \( $(INST_CLEAN_RULE) \) -delete
	find -H $(INSTALL_DIR)$(NMINET_DIR)/src/ -type f \( $(INST_CLEAN_RULE) \) -delete
	find -H $(INSTALL_DIR)$(NMINET_DIR)/lib/ -type d -name .svn -print0 | xargs -0 /bin/rm -rf
	find -H $(INSTALL_DIR)$(NMINET_DIR)/src/ -type d -name .svn -print0 | xargs -0 /bin/rm -rf
	-chown -R 0:0 $(INSTALL_DIR)$(NMINET_DIR)/lib/
	-chown -R 0:0 $(INSTALL_DIR)$(NMINET_DIR)/src/
	-chmod 0755 $(INSTALL_DIR)$(NMINET_DIR)/src/nminet.py
	-$(TOOLCHAIN_PATH)/bin/python -m compileall -f $(INSTALL_DIR)$(NMINET_DIR)/lib/
	-$(TOOLCHAIN_PATH)/bin/python -m compileall -f $(INSTALL_DIR)$(NMINET_DIR)/src/
	test -x overlay && cp -r overlay/* $(INSTALL_DIR)
	find $(INSTALL_DIR) -type d -name .svn -print0 | xargs -0 rm -fr

.PHONY: all install clean distclean realclean $(DIRS)

