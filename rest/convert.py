import os
import sys
import asyncio
import subprocess
import functools
import os.path
import time
import threading
import logging
import mimetypes
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
IMPORT_FILTERS = {
    '.bib': 'BibTeX_Writer',
    '.bmp': 'draw_bmp_Export',
    '.csv': 'Text - txt - csv (StarCalc)',
    '.dbf': 'dBase',
    '.dif': 'DIF',
    '.doc': 'MS Word 97',
    '.docx': 'Office Open XML Text',
    '.emf': 'draw_emf_Export',
    '.eps': 'draw_eps_Export',
    '.fodg': 'OpenDocument Drawing Flat XML',
    '.fodp': 'OpenDocument Presentation Flat XML',
    '.fods': 'OpenDocument Spreadsheet Flat XML',
    '.fodt': 'OpenDocument Text Flat XML',
    '.gif': 'draw_gif_Export',
    '.html': 'HTML (StarWriter)',
    '.jpg': 'draw_jpg_Export',
    '.ltx': 'LaTeX_Writer',
    '.met': 'draw_met_Export',
    '.odd': 'draw8',
    '.odg': 'impress8_draw',
    '.odp': 'impress8',
    '.ods': 'calc8',
    '.odt': 'writer8',
    '.otg': 'draw8_template',
    '.otp': 'impress8_template',
    '.ots': 'calc8_template',
    '.ott': 'writer8_template',
    '.pbm': 'draw_pbm_Export',
    '.pct': 'draw_pct_Export',
    '.pdb': 'AportisDoc Palm DB',
    '.pdf': 'writer_pdf_Export',
    '.pgm': 'draw_pgm_Export',
    '.png': 'draw_png_Export',
    '.pot': 'MS PowerPoint 97 Vorlage',
    '.potm': 'Impress MS PowerPoint 2007 XML Template',
    '.ppm': 'draw_ppm_Export',
    '.pps': 'MS PowerPoint 97 Autoplay',
    '.ppt': 'MS PowerPoint 97',
    '.pptx': 'Impress MS PowerPoint 2007 XML',
    '.psw': 'PocketWord File',
    '.pwp': 'placeware_Export',
    '.pxl': 'Pocket Excel',
    '.ras': 'draw_ras_Export',
    '.rtf': 'Rich Text Format',
    '.sda': 'StarDraw 5.0 (StarImpress)',
    '.sdc': 'StarCalc 5.0',
    '.sdd': 'StarImpress 5.0',
    '.sdw': 'StarWriter 5.0',
    '.slk': 'SYLK',
    '.stc': 'calc_StarOffice_XML_Calc_Template',
    '.std': 'draw_StarOffice_XML_Draw_Template',
    '.sti': 'impress_StarOffice_XML_Impress_Template',
    '.stw': 'writer_StarOffice_XML_Writer_Template',
    '.svg': 'draw_svg_Export',
    '.svm': 'draw_svm_Export',
    '.swf': 'draw_flash_Export',
    '.sxc': 'StarOffice XML (Calc)',
    '.sxd': 'StarOffice XML (Draw)',
    '.sxi': 'StarOffice XML (Impress)',
    '.sxw': 'StarOffice XML (Writer)',
    '.tiff': 'draw_tif_Export',
    '.txt': 'MediaWiki',
    '.uop': 'UOF presentation',
    '.uos': 'UOF spreadsheet',
    '.uot': 'UOF text',
    '.vor': 'StarWriter 5.0 Vorlage/Template',
    '.wmf': 'draw_wmf_Export',
    '.wps': 'MS_Works',
    '.xhtml': 'XHTML Calc File',
    '.xls': 'MS Excel 97',
    '.xlsx': 'Calc MS Excel 2007 XML',
    '.xlt': 'MS Excel 97 Vorlage/Template',
    '.xml': 'DocBook File',
    '.xpm': 'draw_xpm_Export'
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


def input_props(content_type):
    props = {
        "Hidden": True,
        "MacroExecutionMode": 0,
        "ReadOnly": True,
        "Overwrite": True,
        "OpenNewView": True,
        "StartPresentation": False,
        "RepairPackage": False,
    }
    extension = mimetypes.guess_extension(content_type)
    if extension:
        filter = IMPORT_FILTERS.get(extension)
        if filter:
            props["FilterName"] = filter
    return property_tuple(props)


def output_props(doc, output_stream, pages=None):
    filter = PDF_FILTERS[DEFAULT_FILTER]
    for k, v in PDF_FILTERS.items():
        if doc.supportsService(k):
            filter = v
            break
    props = property_tuple({
        "FilterName": filter,
        "Overwrite": True,
        "OutputStream": output_stream,
        "ReduceImageResolution": True,
        "MaxImageResolution": 300,
        "SelectPdfVersion": 1,
    })
    if pages:
        page_range = tuple([
            PropertyValue('PageRange', 0, '%i-%i' % pages, 0)
        ])
        page_prop = uno.Any("[]com.sun.star.beans.PropertyValue", page_range)
        props += tuple([
            PropertyValue("FilterData", 0, page_prop, 0)
        ])
    return props


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

    def convert(self, url=None, data=None, content_type=None, pages=None):
        # Ulitmately, this is the function called by convert()
        in_props = input_props(content_type)

        if data:
            in_stream, url = self.input_stream(data)
            in_props += (property("InputStream", in_stream),)

        LOGGER.debug('input_props: %s', pprint.pformat(in_props))

        doc = self.desktop.loadComponentFromURL(url, "_blank", 0, in_props)

        out_stream = OutputStream()
        out_props = output_props(doc, out_stream, pages)

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

            # TODO: for input above MAX_MEMORY, we should probably write
            # output to disk.
            doc.storeToURL("private:stream", out_props)

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
    LOGGER.debug('Converting document, arguments...')
    for i, arg in enumerate(args):
        LOGGER.debug('[%i]: %s', i, arg)
    for n, v in kwargs.items():
        LOGGER.debug('[%s]: %s', n, v)
    return Connection().convert(*args, **kwargs)


async def convert(*args, **kwargs):
    loop = asyncio.get_running_loop()
    # NOTE: the file argument is removed, our convert() function only handles
    # a data buffer or url (which can be a local path).
    f = kwargs.pop('file', None)

    if f:
        # An AsyncSpooledTemporaryFile has a SpooledTemporaryFile as it's
        # _file attribute.
        if hasattr(f, '_file') and getattr(f._file, '_rolled', None) is False:
            # Get a reference to BytesIO.
            f = f._file._file
            kwargs['data'] = f.getvalue()
            LOGGER.debug('Read %i bytes into buffer', f.tell())
        else:
            kwargs['url'] = unohelper.systemPathToFileUrl(f._file.name)
            LOGGER.debug('Using file URL: %s', kwargs['url'])
            LOGGER.debug('File is %i bytes', os.path.getsize(f._file.name))

    # NOTE: we use an executor here for a few reasons:
    # - This call is blocking, so we want it in a background thread. Since it
    #   is mostly I/O, this should be a good choice.
    # - We want to only have one request at a time to soffice. Since we have a
    #   single threaded executor, we achieve this without extra work.
    return await loop.run_in_executor(EXECUTOR, functools.partial(_convert, *args, **kwargs))


# Start the process early.
SOFFICE = SOffice()
