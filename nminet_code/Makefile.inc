
ifndef TOOLCHAIN_PATH
TOOLCHAIN_PATH=/opt/omneon/cross_x86_64_v6t/
endif

export PYTHONPATH=$(TOP)/lib

WSDL2PY=$(TOP)/../unittestpy/bin/wsdl2py
GENERATE_DS=$(TOP)/../unittestpy/bin/generateDS.py
