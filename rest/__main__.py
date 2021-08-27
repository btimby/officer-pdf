import asyncio
import logging

from aiohttp import web
from convert import convert


LOGGER = logging.getLogger()
LOGGER.addHandler(logging.StreamHandler())
logging.getLogger().setLevel(logging.DEBUG)


async def handler(request):
    body = await request.content.read()
    content_type = request.content_type
    pages = request.query.get('pages')
    if pages:
        try:
            pages = tuple(map(int, pages.split('-')))

        except ValueError:
            return web.Response(text='Invalid param pages', status=400)

        if len(pages) != 2:
            return web.Response(text='Param pages must be in form: 1-?', status=400)

    LOGGER.debug('Body content_type: %s', content_type)
    LOGGER.info('Body read: %i bytes', len(body))

    try:
        pdf = await convert(body, content_type=content_type, pages=pages)

    except Exception as e:
        LOGGER.exception(e)
        return web.Response(text='Internal Server Error', status=500)

    else:
        response = web.Response(body=pdf)
        response.content_type = 'application/pdf'

    return response


app = web.Application()
app.add_routes([web.post('/', handler)])
web.run_app(app)
