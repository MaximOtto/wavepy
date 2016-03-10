from __future__ import print_function
import numpy as np
from scipy import signal

from pywav import *


class Filter(object):
    def __init__ (self, f, sr, numtaps=100, nchannels=0):
        self.numtaps = numtaps
        self.taps = signal.firwin(numtaps=self.numtaps, cutoff=f, window=('kaiser', 8.0), nyq=sr / 2)
        self.states = np.zeros((nchannels, numtaps - 1), dtype=np.float)
        print('states shape ', self.states.shape)
    def process(self, data):
        data, self.states = signal.lfilter(self.taps, 1.0, data,zi=self.states)
        return data

def interleave(multiplier, data):
    output = np.zeros((data.shape[0], data.shape[1] * multiplier), dtype=data.dtype)
    output[:, ::multiplier] = data
    return output

def upsample(multiplier, data)

inp = WavFile('sweep-6dB_24.wav')
out = WavFile_Write('_.wav', 1, 2, 96000, 24)

fff = Filter(20000, 192000, numtaps=2000, nchannels=1)

buf_len = 8192
read = 0

while read < inp._nframes:
    buf = inp.readframes(buf_len, nd=True)
    # buf[0] = fff.process(buf[0])
    buf = interleave(3, buf)
    # print(buf.shape)
    buf[0] = fff.process(buf[:1,])
    # buf[0] *= 3
    buf = buf.reshape(-1, order='F')
    out.writeframes(buf)
    read += buf_len
    if inp._nframes - read < buf_len:
        buf_len = inp._nframes - read

