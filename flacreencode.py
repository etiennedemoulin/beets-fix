#!/usr/bin/env python

# This program is released under the following MIT license:

# Copyright 2016-2019 Jan-Philip Gehrcke (https://gehrcke.de)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
FLAC audio files may have been encoded with errors (using unusual or even
erroneous parameters) that can trip up some FLAC stream decoders whereas the
audio data is not actually damanged. In these cases, re-encoding the audio data
with proper tooling repairs the audio file. The repaired file can then be played
without problems by a program that was unable to play or seek within the
original.

Specifically, I have seen the following behavior for some FLAC audio files
downloaded from Bandcamp: when played in Traktor (Native Instruments, versions
2.10.x) the playback might stop when quickly seeking through the file. For every
affected file the problem went away after re-encoding the audio stream using
(lib)flac.

This is how such a FLAC stream encoding error manifests itself when the flac
program/library comes across it:

    <filename>: ERROR got FLAC__STREAM_DECODER_ERROR_STATUS_LOST_SYNC while decoding FLAC input

This is how such a FLAC stream encoding error manifests itself when ffmpeg comes
across it:

    ...
    Stream mapping:
      Stream #0:0 -> #0:0 (flac (native) -> flac (native))
    Press [q] to stop, [?] for help
    [flac @ 0000000000618560] invalid sync code
    [flac @ 0000000000618560] invalid frame header
    [flac @ 0000000000618560] decode_frame() failed
    Error while decoding stream #0:0: Invalid data found when processing input
    size=   17431kB time=00:02:13.42 bitrate=1070.3kbits/s speed= 267x
    ...


After repairing, the corresponding output looks like that:

    ...
    Stream mapping:
      Stream #0:0 -> #0:0 (flac (native) -> flac (native))
    Press [q] to stop, [?] for help
    size=   15944kB time=00:02:03.61 bitrate=1056.6kbits/s speed= 247x
    ...


The re-encoding method used by this program (via the `flac` program) fully
retains all metadata in a FLAC file, including embedded images. I have confirmed
this with the `metaflac` program (interestingly, re-encoding using ffmpeg would
not retain all data).

For the decoding errors that this re-encoding method is supposed to fix,
notably, the audio data is fully retained. That is, the problem itself does not
mean that the audio data is damaged. The re-encoding simply extracts the good
information and re-writes it in a more compliant way. I have confirmed this with
metaflac by looking at the MD5 checksum of the audio data of an affected FLAC
audio file:

Metaflac STREAMINFO output for the flawed FLAC file:

    METADATA block #0
      type: 0 (STREAMINFO)
      is last: false
      length: 34
      minimum blocksize: 4096 samples
      maximum blocksize: 4096 samples
      minimum framesize: 7585 bytes
      maximum framesize: 20347 bytes
      sample_rate: 44100 Hz
      channels: 2
      bits-per-sample: 24
      total samples: 26226176
      MD5 signature: cd0d4691df20a8060312977cc7af64d9

Metaflac STREAMINFO output for the corresponding repaired (re-encoded) file:

    METADATA block #0
      type: 0 (STREAMINFO)
      is last: false
      length: 34
      minimum blocksize: 1152 samples
      maximum blocksize: 1152 samples
      minimum framesize: 2046 bytes
      maximum framesize: 6092 bytes
      sample_rate: 44100 Hz
      channels: 2
      bits-per-sample: 24
      total samples: 26226176
      MD5 signature: cd0d4691df20a8060312977cc7af64d9

The checksum, i.e. the audio data, remained the same, bit by bit. Notably, the
maximum frame size and a few other details changed, indicating that the original
file was encoded with unusual parameters that can trip up decoders.

This program uses the official `flac` program which is documented at
https://xiph.org/flac/documentation_tools_flac.html
"""

import datetime
import logging
import os
import platform
import random
import shutil
import string
import subprocess
import sys

log = logging.getLogger()

WINDOWS = platform.system() == 'Windows'

def rnd_string(N):
    return ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=N))

def process_flac_file(flac_executable_path, filepath):

    output_filepath_suffix = '%s.reenc.flac' % (rnd_string(6), )
    relative_input_filepath = filepath.split('/')[-1]
    parent_folder = "/".join(filepath.split('/')[:-1])
    output_filepath_tmp = parent_folder + "/" + relative_input_filepath + output_filepath_suffix

    flac_cmd = [
        flac_executable_path,
        '--verify',
#        '--compression-level-0',
        '--decode-through-errors',
        '--preserve-modtime',
        '--silent',
        '-o',
        output_filepath_tmp,
        filepath
    ]

    sp = subprocess.run(
        flac_cmd,
        stderr=subprocess.STDOUT,
 #       stdout=subprocess.DEVNULL
    )

#    check = input("Remove original file and replace by fixed one ? Please check the output of fix command first! (y/n)")
#    if check == 'y':
    os.remove(filepath)
    movefile(output_filepath_tmp, relative_input_filepath)
#    else:
#        print('this file will now be removed ', output_filepath_tmp)
#        os.remove(output_filepath_tmp)

    # last check with flac --test
    sp2 = subprocess.run(
        [flac_executable_path, '--test', relative_input_filepath],
        stderr=subprocess.STDOUT,
        stdout=subprocess.DEVNULL
    )

    if sp2.returncode == 0:
        print(relative_input_filepath, ': ok')


def movefile(src, dst):
    # Create directory(ies) if not yet existing.

    if os.path.exists(dst):
        raise Exception('Was not expected to exist: %s' % (dst, ))

    # https://bugs.python.org/issue18199#msg191121
    # Well, the problem, as you point out, is that "\\?\" only works with
    # absolute paths, but the stdlib currently works with both absolute and
    # relative paths. The only reasonable solution right now is to prepend the
    # "\\?\" prefix yourself (after having resolved the path to absolute).
    if WINDOWS:
        # log.debug('windows src dst')
        src = "\\\\?\\" + os.path.abspath(src)
        dst = "\\\\?\\" + os.path.abspath(dst)

    dst_dir, _ = os.path.split(dst)
    if dst_dir and not os.path.exists(dst_dir):
        log.debug('Create directory %s', dst_dir)
        os.makedirs(dst_dir, exist_ok=True)

    log.debug('Move `%s` to `%s`', src, dst)
    shutil.move(src, dst)


def main(filepath):
    flac_executable_path = shutil.which('flac')
    absolute_path = os.path.abspath(filepath)
    process_flac_file(flac_executable_path, absolute_path)

if __name__ == "__main__":
    main(sys.argv[1])