"""Stub audioop module for Python 3.13+ compatibility with pydub.
Provides minimal implementations of functions pydub uses internally."""

import struct
import math


def _check_params(len1, len2):
    if len1 != len2:
        raise ValueError("input lengths must match")


def max(fragment, width):
    result = 0
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        if abs(val) > result:
            result = abs(val)
    return result


def maxpp(fragment, width):
    max_pos = 0
    max_neg = 0
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        if val > max_pos:
            max_pos = val
        if val < max_neg:
            max_neg = val
    return max_pos, abs(max_neg)


def avg(fragment, width):
    total = 0
    count = len(fragment) // width
    if count == 0:
        return 0
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        total += struct.unpack_from(fmt, fragment, i)[0]
    return total // count


def avgpp(fragment, width):
    total = 0
    count = len(fragment) // width
    if count == 0:
        return 0
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        total += abs(struct.unpack_from(fmt, fragment, i)[0])
    return total // count


def rms(fragment, width):
    total = 0
    count = len(fragment) // width
    if count == 0:
        return 0
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        total += val * val
    return int(math.sqrt(total / count))


def findmax(fragment, length):
    fmt = {1: 'b', 2: 'h', 4: 'i'}[2]  # pydub uses 16-bit
    best_val = 0
    best_idx = 0
    for i in range(0, len(fragment) - 1, 2):
        val = abs(struct.unpack_from(fmt, fragment, i)[0])
        if val > best_val:
            best_val = val
            best_idx = i // 2
    return best_idx


def findfit(fragment, reference):
    return (0, 0)


def cross(fragment, width):
    total = 0
    prev = 0
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        if (prev < 0 and val >= 0) or (prev >= 0 and val < 0):
            total += 1
        prev = val
    return total


def mul(fragment, width, factor):
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    result = bytearray(len(fragment))
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        struct.pack_into(fmt, result, i, val * factor)
    return bytes(result)


def tomono(fragment, width, lfactor, rfactor):
    return fragment[:len(fragment)//2]


def tostereo(fragment, width, lfactor, rfactor):
    result = bytearray(len(fragment) * 2)
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        struct.pack_into(fmt, result, i * 2, val * lfactor)
        struct.pack_into(fmt, result, i * 2 + width, val * rfactor)
    return bytes(result)


def getsample(fragment, width, index):
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    return struct.unpack_from(fmt, fragment, index * width)[0]


def add(fragment1, fragment2, width):
    _check_params(len(fragment1), len(fragment2))
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    result = bytearray(len(fragment1))
    for i in range(0, len(fragment1), width):
        v1 = struct.unpack_from(fmt, fragment1, i)[0]
        v2 = struct.unpack_from(fmt, fragment2, i)[0]
        struct.pack_into(fmt, result, i, v1 + v2)
    return bytes(result)


def bias(fragment, width, bias):
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    result = bytearray(len(fragment))
    for i in range(0, len(fragment), width):
        val = struct.unpack_from(fmt, fragment, i)[0]
        struct.pack_into(fmt, result, i, val + bias)
    return bytes(result)


def reverse(fragment, width):
    result = bytearray(len(fragment))
    count = len(fragment) // width
    for i in range(count):
        src_start = i * width
        dst_start = (count - 1 - i) * width
        result[dst_start:dst_start+width] = fragment[src_start:src_start+width]
    return bytes(result)


def lin2lin(fragment, width, newwidth):
    if width == newwidth:
        return fragment
    result = bytearray(len(fragment) * newwidth // width)
    fmt_old = {1: 'b', 2: 'h', 4: 'i'}[width]
    fmt_new = {1: 'b', 2: 'h', 4: 'i'}[newwidth]
    for i in range(len(fragment) // width):
        val = struct.unpack_from(fmt_old, fragment, i * width)[0]
        struct.pack_into(fmt_new, result, i * newwidth, val)
    return bytes(result)


def ratecv(fragment, width, nchannels, inrate, outrate, state, weightA, weightB):
    ratio = outrate / inrate
    new_len = int(len(fragment) / width * ratio)
    result = bytearray(new_len * width)
    fmt = {1: 'b', 2: 'h', 4: 'i'}[width]
    for i in range(new_len):
        src_idx = int(i / ratio) * width
        if src_idx + width <= len(fragment):
            struct.pack_into(fmt, result, i * width,
                           struct.unpack_from(fmt, fragment, src_idx)[0])
    return bytes(result), state


def ulaw2lin(fragment, width):
    return fragment


def alaw2lin(fragment, width):
    return fragment


def lin2ulaw(fragment, width):
    return fragment


def lin2alaw(fragment, width):
    return fragment


def adpcm2lin(fragment, width, state):
    return fragment, state


def lin2adpcm(fragment, width, state):
    return fragment, state
