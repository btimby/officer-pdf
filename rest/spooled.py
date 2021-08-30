import asyncio
import tempfile

from functools import partial
from aiofiles.base import AiofilesContextManager
from aiofiles.tempfile import AsyncSpooledTemporaryFile


class _NamedSpooledTemporaryFile(tempfile.SpooledTemporaryFile):
    def rollover(self):
        if self._rolled: return
        file = self._file
        newfile = self._file = tempfile.NamedTemporaryFile(**self._TemporaryFileArgs)
        del self._TemporaryFileArgs

        pos = file.tell()
        if hasattr(newfile, 'buffer'):
            newfile.buffer.write(file.detach().getvalue())
        else:
            newfile.write(file.getvalue())
        newfile.seek(pos, 0)

        self._rolled = True


async def _spooled_temporary_file(max_size=0, mode='w+b', buffering=-1,
                                  encoding=None, newline=None, suffix=None,
                                  prefix=None, dir=None, loop=None, executor=None):
    """Open a spooled temporary file with async interface"""
    if loop is None:
        loop = asyncio.get_event_loop()

    cb = partial(_NamedSpooledTemporaryFile, max_size=max_size, mode=mode,
                 buffering=buffering, encoding=encoding,
                 newline=newline, suffix=suffix,
                 prefix=prefix, dir=dir)

    f = await loop.run_in_executor(executor, cb)

    # Single interface provided by SpooledTemporaryFile for all modes
    return AsyncSpooledTemporaryFile(f, loop=loop, executor=executor)


def NamedSpooledTemporaryFile(*args, **kwargs):
    return AiofilesContextManager(_spooled_temporary_file(*args, **kwargs))
