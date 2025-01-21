import pytest
from sanic import Sanic
from sanic import response
from sanic_testing.testing import SanicTestClient

from swagger_ui import api_doc

from .common import config_content
from .common import kwargs_list


@pytest.fixture
def app():
    app = Sanic('test_sanic')

    @app.get(r'/hello/world')
    async def index_handler(request):
        return response.text('Hello World!!!')
    return app


@pytest.mark.parametrize('kwargs', kwargs_list)
def test_sanic(app, kwargs):
    if kwargs.get('config_rel_url'):
        @app.get(kwargs['config_rel_url'])
        async def swagger_config_handler(request):
            return response.json(config_content)

    api_doc(app, **kwargs)

    url_prefix = kwargs['url_prefix']
    if url_prefix.endswith('/'):
        url_prefix = url_prefix[:-1]

    client = SanicTestClient(app)
    _, resp = client.get('/hello/world')
    assert resp
    assert resp.status == 200, resp.text

    _, resp = client.get(url_prefix)
    assert resp
    assert resp.status == 200, resp.text

    _, resp = client.get(f'{url_prefix}/static/LICENSE')
    assert resp
    assert resp.status == 200, resp.text

    if kwargs.get('editor'):
        _, resp = client.get(f'{url_prefix}/editor')
        assert resp
        assert resp.status == 200, resp.text
    else:
        _, resp = client.get(f'{url_prefix}/editor')
        assert resp
        assert resp.status == 404, resp.text

    if kwargs.get('config_rel_url'):
        _, resp = client.get(kwargs['config_rel_url'])
        assert resp
        assert resp.status == 200, resp.text
    else:
        _, resp = client.get(f'{url_prefix}/swagger.json')
        assert resp
        assert resp.status == 200, resp.text
