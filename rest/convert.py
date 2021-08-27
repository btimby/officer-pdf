import os
import sys
import asyncio
import subprocess
import functools
import os.path
import time
import threading
import logging
import pprint

from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from tempfile import gettempdir

import uno
import unohelper
from com.sun.star.beans import PropertyValue
from com.sun.star.lang import DisposedException, IllegalArgumentException
from com.sun.star.connection import NoConnectException
from com.sun.star.io import IOException, XOutputStream
from com.sun.star.script import CannotConvertException
from com.sun.star.uno import RuntimeException


# NOTE: 1 is strongly encouraged, to restrict client connections to 1 at a
# time.
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", 1))
# A pool of workers to perform conversions to pdf.
EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)

SOFFICE = None
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

DEFAULT_FILTER = "com.sun.star.text.GenericTextDocument"
PDF_FILTERS = {
    "com.sun.star.text.GenericTextDocument": "writer_pdf_Export",
    "com.sun.star.text.WebDocument": "writer_web_pdf_Export",
    "com.sun.star.presentation.PresentationDocument": "impress_pdf_Export",
    "com.sun.star.drawing.DrawingDocument": "draw_pdf_Export",
}


def property(name, value):
    prop = PropertyValue()
    prop.Name = name
    prop.Value = value
    return prop


def property_tuple(d):
    properties = []
    for k, v in d.items():
        properties.append(property(k, v))
    return tuple(properties)


def input_props(input_stream):
    return property_tuple({
        "InputStream": input_stream,
        "Hidden": True,
        "MacroExecutionMode": 0,
        "ReadOnly": True,
        "Overwrite": True,
        "OpenNewView": True,
        "StartPresentation": False,
        "RepairPackage": False,
    })


def output_props(doc, output_stream):
    filter = PDF_FILTERS[DEFAULT_FILTER]
    for k, v in PDF_FILTERS.items():
        if doc.supportsService(k):
            filter = v
            break
    return property_tuple({
        "FilterName": filter,
        "Overwrite": True,
        "OutputStream": output_stream,
        "ReduceImageResolution": True,
        "MaxImageResolution": 300,
        "SelectPdfVersion": 1,
    })



class OutputStream(unohelper.Base, XOutputStream):
    """
    Simple class to receive pdf from soffice.
    """
    def __init__(self):
        self.f = BytesIO()
        self.closed = False

    def closeOutput(self):
        self.closed = True

    def writeBytes(self, seq):
        if self.closed:
            raise IOError('write to closed stream')
        try:
            self.f.write(seq.value)
        except Exception as e:
            LOGGER.exception(e)
            raise

    def getvalue(self):
        return self.f.getvalue()

    def flush(self):
        pass


class Connection(object):
    """
    Manages connection to soffice.

    This class handles all the details of the conversion.
    """
    def __init__(self):
        self.context = uno.getComponentContext()
        self.service_manager = self.context.ServiceManager
        resolver = self.service_manager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", self.context)
        ctx = resolver.resolve('uno:%s' % SOffice.ADDRESS)
        self.desktop = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)

    def input_stream(self, data):
        stream = self.service_manager.createInstanceWithContext(
            "com.sun.star.io.SequenceInputStream", self.context)
        seq = uno.ByteSequence(data)
        # NOTE: the call below passes a tuple.
        stream.initialize((seq,))
        return stream, "private:stream"

    def output_stream(self):
        return OutputStream(), "private:stream"

    def convert(self, file_data, content_type=None, pages=None):
        # Ulitmately, this is the function called by convert()
        in_stream, in_url = self.input_stream(file_data)
        out_stream, out_url = self.output_stream()

        in_props = input_props(in_stream)
        LOGGER.debug('in_url: %s', in_url)
        LOGGER.debug('input_props: %s', pprint.pformat(in_props))

        doc = self.desktop.loadComponentFromURL(in_url, "_blank", 0, in_props)

        out_props = output_props(doc, out_stream)

        if pages:
            page_range = tuple([
                PropertyValue('PageRange', 0, '%i-%i' % pages, 0)
            ])
            page_prop = uno.Any("[]com.sun.star.beans.PropertyValue", page_range)
            out_props += tuple([
                PropertyValue("FilterData", 0, page_prop, 0)
            ])

        LOGGER.debug('out_url: %s', out_url)
        LOGGER.debug('output_props: %s', pprint.pformat(out_props))

        try:
            try:
                doc.ShowChanges = False
            except AttributeError:
                pass
            
            try:
                doc.refresh()
            except AttributeError:
                pass


            doc.storeToURL(out_url, out_props)

        finally:
            doc.dispose()
            doc.close(True)
        
        pdf = out_stream.getvalue()
        LOGGER.debug('len(out_stream): %s', len(pdf))
        return pdf


class SOffice(object):
    """
    Execute soffice and monitor process health.

    This thread runs soffice, sends it's output to stdout / stderr and
    restarts it if necessary.
    """
    ADDRESS = "socket,host=localhost,port=2002,tcpNoDelay=1;urp;StarOffice.ComponentContext"
    INSTALL_DIR = os.path.join(gettempdir(), "soffice")
    COMMAND = [
        "/usr/bin/soffice",
        "-env:UserInstallation=file:///%s" % INSTALL_DIR,
        "-env:JFW_PLUGIN_DO_NOT_CHECK_ACCESSIBILITY=1",
        "--nologo",
        "--headless",
        "--invisible",
        "--nocrashreport",
        "--nodefault",
        "--norestore",
        "--safe-mode",
        "--accept=%s" % ADDRESS,
    ]

    def __init__(self):
        self.p = None
        self.t = threading.Thread(target=self._run)
        self.t.start()

    def _run(self):
        while True:
            if self.p is None:
                LOGGER.info('Starting soffice')
                self.p = subprocess.Popen(
                    SOffice.COMMAND,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
            
            while self.p.poll() is None:
                try:
                    out, err = self.p.communicate(timeout=1.0)
                    if out:
                        LOGGER.info('soffice stdout: %s', out)
                    if err:
                        LOGGER.info('soffice stderr: %s', err)

                except subprocess.TimeoutExpired:
                    pass

            LOGGER.warning('Exited with returncode: %s', self.p.returncode)
            time.sleep(1.0)


def _convert(*args, **kwargs):
    LOGGER.debug('Converting document')
    return Connection().convert(*args, **kwargs)


async def convert(*args, **kwargs):
    loop = asyncio.get_running_loop()
    # NOTE: we use an executor here for a few reasons:
    # - This call is blocking, so we want it in a background thread. Since it
    #   is mostly I/O, this should be a good choice.
    # - We want to only have one request at a time to soffice. Since we have a
    #   single threaded executor, we achieve this without extra work.
    return await loop.run_in_executor(EXECUTOR, functools.partial(_convert, *args, **kwargs))


# Start the process early.
SOFFICE = SOffice()
