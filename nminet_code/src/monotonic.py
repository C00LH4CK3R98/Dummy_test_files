#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import ctypes
import ctypes.util

__all__ = ["monotonic"]

try:
    _clock_gettime = ctypes.CDLL(ctypes.util.find_library('c'),
                                use_errno=True).clock_gettime
except AttributeError:
    _clock_gettime = ctypes.CDLL(ctypes.util.find_library('rt'),
                                use_errno=True).clock_gettime

class _timespec(ctypes.Structure):
    """Time specification, as described in clock_gettime(3)."""
    _fields_ = (('tv_sec', ctypes.c_long),
                ('tv_nsec', ctypes.c_long))

CLOCK_MONOTONIC_RAW = 4         # >= Linux 2.6.28 required

def monotonic():
    """Monotonic clock, cannot go backward.
       Not affected by NTP adjustments
    """

    ts = _timespec()

    if _clock_gettime(CLOCK_MONOTONIC_RAW, ctypes.pointer(ts)):
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))

    return ts.tv_sec + ts.tv_nsec * 1e-9


if __name__ == "__main__":
    import time

    # Perform a sanity-check.
    if monotonic() - monotonic() >= 0:
        raise ValueError('monotonic() is not monotonic!')

    print(monotonic())
    time.sleep(1)
    print(monotonic())

