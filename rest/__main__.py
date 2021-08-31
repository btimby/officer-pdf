import os
import json
import asyncio
import logging
import mimetypes
import aiofiles
import aiohttp
import os.path

from functools import partial
from io import BytesIO
from aiohttp import web

from convert import convert
from config import (
    MAX_CHUNK, MAX_MEMORY, TEMP_DIR, MAX_CONCURRENCY,
)
from spooled import NamedSpooledTemporaryFile

LOGGER = logging.getLogger()
LOGGER.addHandler(logging.StreamHandler())
logging.getLogger().setLevel(logging.DEBUG)


async def copyfileobj(src, dst, length=None):
    size = 0
    while True:
        chunk = await src.read(length)
        if not chunk:
            break
        size += len(chunk)
        await dst.write(chunk)
    await dst.flush()
    return size


async def download(url, **kwargs):
    async with aiohttp.ClientSession(**kwargs) as s:
        async with s.get(url) as r:
            extension = mimetypes.guess_extension(r.headers['content-type'])
            temp = NamedSpooledTemporaryFile(
                max_size=MAX_MEMORY, mode='wb+', dir=TEMP_DIR, suffix=extension)

            size = await copyfileobj(request.content, temp, length=MAX_CHUNK)
            return temp, size


async def head(url):
    async with aiohttp.ClientSession() as s:
        async with s.head(url) as r:
            content_type = r.headers['content-type']
            size = int(r.headers['content-length'])
            return content_type.split(';')[0], size


def get_pages(request):
    pages = request.query.get('pages')

    if pages:
        try:
            pages = tuple(map(int, pages.split('-')))

        except ValueError:
            raise web.HTTPBadRequest(reason='Invalid param pages')

        if len(pages) != 2:
            raise web.HTTPBadRequest(reason='Param pages must be in form: 1-?')

    return pages


class TempfileResponse(web.FileResponse):
    '''
    A FileResponse subclass that cleans up the file after the response.
    '''
    async def prepare(self, *args, **kwargs):
        try:
            return await super(TempfileResponse, self).prepare(
                *args, **kwargs)

        finally:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, partial(os.unlink, self._path))


def make_response(pdf):
    if isinstance(pdf, BytesIO):
        response = web.Response(body=pdf.getvalue())
    
    else:
        response = TempfileResponse(path=pdf.name)

    response.content_type = 'application/pdf'
    return response


async def pdf_get(request):
    url, headers, cookies = request.query.get('url'), None, None
    kwargs = {}

    if url.startswith('http'):
        # This is a remote URL, could be additional options provided.
        headers = request.query.get('headers')
        cookies = request.query.get('cookies')

    else:
        # This is a local URL, try to guess the content_type.
        kwargs['url'], (kwargs['content_type'], _) = \
            url, mimetypes.guess_type(url)
        kwargs['size'] = os.path.getsize(url)

    if headers or cookies:
        # We have to do the fetch, soffice does not support headers or other
        # advanced options.
        headers = json.loads(headers)
        cookies = json.loads(cookies)

        kwargs['file'], kwargs['content_type'], kwargs['size'] = \
             await download(url, headers=headers, cookies=cookies)

    else:
        # We will let soffice do the request. We omit content_type here, as
        # soffice can use the Content-Type header it receives.
        kwargs['url'] = url
        kwargs['content_type'], kwargs['size'] = await head(url)

    try:
        pdf = await convert(**kwargs)

    except Exception as e:
        LOGGER.exception(e)
        raise web.HTTPInternalServerError(reason='Internal Server Error')

    finally:
        f = kwargs.get('file')
        if hasattr(f, '_file') and getattr(f._file, '_rolled', None) is True:
            f = f._file._file
            os.unlink(f.name)

    return make_response(pdf)


async def pdf_post(request):
    content_type = request.content_type
    pages = get_pages(request)
    extension = mimetypes.guess_extension(content_type)

    async with NamedSpooledTemporaryFile(
        max_size=MAX_MEMORY, mode='w+b', dir=TEMP_DIR,
        suffix=extension) as temp:

        size = await copyfileobj(request.content, temp, length=MAX_CHUNK)

        LOGGER.debug('Body content_type: %s', content_type)
        LOGGER.info('Body read: %i bytes', await temp.tell())

        try:
            pdf = await convert(
                file=temp, content_type=content_type, pages=pages, size=size)

        except Exception as e:
            LOGGER.exception(e)
            raise web.HTTPInternalServerError(reason='Internal Server Error')

        return make_response(pdf)


async def health(request):
    try:
        pdf = await convert(data=b'Health check', content_type='text/plain')

    except Exception as e:
        LOGGER.exception(e)
        return web.Response(text='ERROR', status=503)

    else:
        return web.Response(text='OK')


LOGGER.debug('MAX_CONCURRENCY: %i', MAX_MEMORY)
LOGGER.debug('MAX_MEMORY: %i', MAX_MEMORY)
LOGGER.debug('MAX_CHUNK: %i', MAX_MEMORY)
LOGGER.debug('TEMP_DIR: %i', MAX_MEMORY)

app = web.Application()
app.add_routes([
    web.get('/', health),
    web.get('/pdf/', pdf_get),
    web.post('/pdf/', pdf_post)
])
web.run_app(app)
