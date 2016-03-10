import numpy as np

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xfffe

GUID_PCM =   '\x01\x00\x00\x00\x00\x00\x10\x00\x80\x00\x00\xAA\x00\x38\x9B\x71'
GUID_FLOAT = '\x03\x00\x00\x00\x00\x00\x10\x00\x80\x00\x00\xAA\x00\x38\x9B\x71'


_array_fmts = None, 'b', 'h', None, 'i'

import struct
import sys
from chunk import Chunk

def _byteswap3(data):
    ba = bytearray(data)
    ba[::3] = data[2::3]
    ba[2::3] = data[::3]
    return bytes(ba)

class WavFile(object):
    def __init__(self, path):
        self._convert = None
        self._soundpos = 0
        file_ = open(path, 'rb')
        self._file = Chunk(file_, bigendian = 0)
        if self._file.getname() != 'RIFF':
            raise Error, 'file does not start with RIFF id'
        if self._file.read(4) != 'WAVE':
            raise Error, 'not a WAVE file'
        self._fmt_chunk_read = 0
        self._data_chunk = None
        while 1:
            self._data_seek_needed = 1
            try:
                chunk = Chunk(self._file, bigendian = 0)
            except EOFError:
                break
            chunkname = chunk.getname()
            if chunkname == 'fmt ':
                self._read_fmt_chunk(chunk)
                self._fmt_chunk_read = 1
            elif chunkname == 'data':
                if not self._fmt_chunk_read:
                    raise Error, 'data chunk before fmt chunk'
                self._data_chunk = chunk
                self._nframes = chunk.chunksize // self._framesize
                self._data_seek_needed = 0
                break
            chunk.skip()
        if not self._fmt_chunk_read or not self._data_chunk:
            raise Error, 'fmt chunk and/or data chunk missing'

    def _read_fmt_chunk(self, chunk):
        chunk_size = chunk.getsize()
        self._wFormatTag, self._nchannels, self._framerate, \
        dwAvgBytesPerSec, wBlockAlign, wBitsPerSample  = struct.unpack('<HHLLHH', chunk.read(16))
        if chunk_size > 16:
            cbSize = struct.unpack('<H', chunk.read(2))[0]

        if self._wFormatTag not in [WAVE_FORMAT_PCM, WAVE_FORMAT_IEEE_FLOAT, WAVE_FORMAT_EXTENSIBLE]:
            raise Error, 'unknown format: %r' % (wFormatTag,)

        if self._wFormatTag == WAVE_FORMAT_EXTENSIBLE:
            union, dwChannelMask = struct.unpack('<HL', chunk.read(6))
            self._SubFormat = chunk.read(16)
            print union, hex(dwChannelMask), dwChannelMask
            print self._SubFormat.encode('hex')
        self._sampwidth = (wBitsPerSample + 7) // 8
        self._framesize = self._nchannels * self._sampwidth
        self._comptype = 'NONE'
        self._compname = 'not compressed'

    def readframes(self, nframes, nd=False):
        if self._data_seek_needed:
            self._data_chunk.seek(0, 0)
            pos = self._soundpos * self._framesize
            if pos:
                self._data_chunk.seek(pos, 0)
            self._data_seek_needed = 0
        if nframes == 0:
            return ''
        if self._sampwidth in (2, 4) and sys.byteorder == 'big':
            # unfortunately the fromfile() method does not take
            # something that only looks like a file object, so
            # we have to reach into the innards of the chunk object
            import array
            chunk = self._data_chunk
            data = array.array(_array_fmts[self._sampwidth])
            assert data.itemsize == self._sampwidth
            nitems = nframes * self._nchannels
            if nitems * self._sampwidth > chunk.chunksize - chunk.size_read:
                nitems = (chunk.chunksize - chunk.size_read) / self._sampwidth
            data.fromfile(chunk.file.file, nitems)
            # "tell" data chunk how much was read
            chunk.size_read = chunk.size_read + nitems * self._sampwidth
            # do the same for the outermost chunk
            chunk = chunk.file
            chunk.size_read = chunk.size_read + nitems * self._sampwidth
            data.byteswap()
            data = data.tostring()
        else:
            # data = self._data_chunk.read(nframes * self._framesize)
            # if self._sampwidth == 3 and sys.byteorder == 'big':
            #     data = _byteswap3(data)

            if self._wFormatTag == WAVE_FORMAT_PCM or\
                    self._wFormatTag == WAVE_FORMAT_EXTENSIBLE and self._SubFormat == GUID_PCM:
                if 2 == self._sampwidth:
                    data = np.frombuffer(self._data_chunk.read(nframes * self._framesize), dtype=np.int16)
                    data = data.astype(np.float)
                    data = np.divide(data, 0x8000)
                elif 4 == self._sampwidth:
                    data = np.frombuffer(self._data_chunk.read(nframes * self._framesize), dtype=np.int32)
                    data = data.astype(np.float)
                    data = np.divide(data, 0x80000000)
                elif 3 == self._sampwidth:
                    ints = np.zeros(nframes * self._nchannels, dtype=np.int32)
                    raw_data = np.frombuffer(self._data_chunk.read(nframes * self._framesize), dtype=np.uint8)
                    raw_data = raw_data.astype(np.int32)

                    for byte_pos, shift_val in zip(reversed(range(self._sampwidth)), reversed(range(0, 32, 8))):
                        ints = np.bitwise_or(ints, np.left_shift(raw_data[byte_pos::self._sampwidth], shift_val))

                    data = np.divide(ints.astype(np.float), 0x80000000)

                else:
                    raise Error, 'samplewidth is not 16, 24 or 32 bits'

            elif self._wFormatTag == WAVE_FORMAT_IEEE_FLOAT or\
                    self._wFormatTag == WAVE_FORMAT_EXTENSIBLE and self._SubFormat == GUID_FLOAT:
                data = np.frombuffer(self._data_chunk.read(nframes * self._nchannels), dtype=np.float32)

            else:
                raise Error, 'unexpected GUID'

        # if self._convert and data:
        #     data = self._convert(data)
        self._soundpos = self._soundpos + len(data) // (self._nchannels * self._sampwidth)

        if nd:
            data = data.reshape(self._nchannels, data.size / self._nchannels, order='F')

        return data

class WavFile_Write(object):
    def __init__(self, path, wFormatTag, nChannels, nSamplesPerSec, wBitsPerSample):
        self._wFormatTag = wFormatTag
        self._nchannels = nChannels
        self._nSamplesPerSec = nSamplesPerSec
        self._wBitsPerSample = wBitsPerSample
        self._file = open(path, 'wb')
        self._datalength = 0

        self._sampwidth = wBitsPerSample // 8

        self._nframes = 0
        self._nframeswritten = 0
        self._datawritten = 0
        self._datalength = 0

        ######
        self._form_length_pos = 4
        self._data_length_pos = 40
        ######
        self.comment = None

        nAvgBytesPerSec = nChannels * nSamplesPerSec * (wBitsPerSample / 8)
        nBlockAlign = self._sampwidth * nChannels
        print nBlockAlign
        header = struct.pack('<4sL4s4sLHHLLHH4sL',
            'RIFF', 36 + self._datalength, 'WAVE', 'fmt ', 16,
            wFormatTag, nChannels, nSamplesPerSec,
            nAvgBytesPerSec,
            nBlockAlign,
            wBitsPerSample,
            'data', self._datalength)

        self._file.write(header)

    def writeframesraw(self, data):
        nframes = len(data) // (self._nchannels)

        if self._wFormatTag == WAVE_FORMAT_PCM and 2 == self._sampwidth:
            data_to_write = np.multiply(data, 0x7fff)
            data_to_write.astype(np.int16).tofile(self._file)

        elif self._wFormatTag == WAVE_FORMAT_PCM and 4 == self._sampwidth:
            data_to_write = np.multiply(data, 0x7fffffff)
            data_to_write.astype(np.int32).tofile(self._file)

        elif self._wFormatTag == WAVE_FORMAT_PCM and 3 == self._sampwidth:
            data = np.multiply(data, 0x7fffffff)
            data = data.astype(np.int32)
            bytes = np.zeros(data.size * 3, dtype=np.uint8)

            bytes[0::3] = np.right_shift(data, 8)
            bytes[1::3] = np.right_shift(data, 16)
            bytes[2::3] = np.right_shift(data, 24)

            bytes.tofile(self._file)

        elif self._wFormatTag == WAVE_FORMAT_IEEE_FLOAT and 4 == self._sampwidth:
            data.tofile(self._file)

        else:
            print 'oops'

        self._datawritten = self._datawritten + (len(data) * self._sampwidth)
        self._nframeswritten = self._nframeswritten + nframes

    def writeframes(self, data):
        self.writeframesraw(data)
        if self._datalength != self._datawritten:
            self._patchheader()

    def _patchheader(self):
        if self._datawritten == self._datalength:
            return
        curpos = self._file.tell()
        self._file.seek(self._form_length_pos, 0)
        self._file.write(struct.pack('<L', 36 + self._datawritten))
        self._file.seek(self._data_length_pos, 0)
        self._file.write(struct.pack('<L', self._datawritten))
        self._file.seek(curpos, 0)
        self._datalength = self._datawritten

    def write_comment(self):
        comment_length = len(self.comment)
        self._file.write('COMM')
        self._file.write(struct.pack('<L', comment_length))
        self._file.write(self.comment)