import falcon
import pytest
from falcon import testing

from swagger_ui import api_doc

from .common import config_content
from .common import kwargs_list


@pytest.fixture
def app():
    class HelloWorldHandler:
        def on_get(self, req, resp):
            resp.text = 'Hello World!!!'

    app = falcon.App()

    app.add_route('/hello/world', HelloWorldHandler())
    return app


@pytest.mark.parametrize('kwargs', kwargs_list)
def test_falcon(app, kwargs):
    if kwargs['url_prefix'] in ('', '/'):
        return

    if kwargs.get('config_rel_url'):
        class SwaggerConfigHandler(object):
            def on_get(self, req, resp):
                resp.body = config_content
        app.add_route(kwargs['config_rel_url'], SwaggerConfigHandler())

    api_doc(app, **kwargs)

    url_prefix = kwargs['url_prefix']
    if url_prefix.endswith('/'):
        url_prefix = url_prefix[:-1]

    client = testing.TestClient(app)

    resp = client.get('/hello/world')
    assert resp.status_code == 200, resp.text

    resp = client.get(url_prefix)
    assert resp.status_code == 200, resp.text

    resp = client.get(f'{url_prefix}/static/LICENSE')
    assert resp.status_code == 200, resp.text

    resp = client.get(f'{url_prefix}/editor')
    if kwargs.get('editor'):
        assert resp.status_code == 200, resp.text
    else:
        assert resp.status_code == 404, resp.text

    if kwargs.get('config_rel_url'):
        resp = client.get(kwargs['config_rel_url'])
        assert resp.status_code == 200, resp.text
    else:
        resp = client.get(f'{url_prefix}/swagger.json')
        assert resp.status_code == 200, resp.text
