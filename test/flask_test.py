import pytest
from flask import Flask

from swagger_ui import api_doc

from .common import config_content
from .common import kwargs_list


@pytest.fixture
def app():
    app = Flask(__name__)

    @app.route(r'/hello/world')
    def hello():
        return 'Hello World!!!'
    return app


@pytest.mark.parametrize('kwargs', kwargs_list)
def test_flask(app, kwargs):
    if kwargs['url_prefix'] in ('/', ''):
        return

    if kwargs.get('config_rel_url'):
        @app.route(kwargs['config_rel_url'])
        def swagger_config():
            return config_content

    api_doc(app, **kwargs)

    url_prefix = kwargs['url_prefix']
    if url_prefix.endswith('/'):
        url_prefix = url_prefix[:-1]

    client = app.test_client()

    resp = client.get('/hello/world')
    assert resp.status_code == 200, resp.data

    resp = client.get(url_prefix)
    assert resp.status_code == 200, resp.data

    resp = client.get(f'{url_prefix}/static/LICENSE')
    assert resp.status_code == 200, resp.data

    resp = client.get(f'{url_prefix}/editor')
    if kwargs.get('editor'):
        assert resp.status_code == 200, resp.data
    else:
        assert resp.status_code == 404, resp.data

    if kwargs.get('config_rel_url'):
        resp = client.get(kwargs['config_rel_url'])
        assert resp.status_code == 200, resp.data
    else:
        resp = client.get(f'{url_prefix}/swagger.json')
        assert resp.status_code == 200, resp.data


def test_fork_configuration_and_oauth(app):
    api_doc(
        app,
        config={"openapi": "3.0.3", "info": {"title": "Fork", "version": "1"}, "paths": {}},
        url_prefix="/private/docs",
        blueprint_name="custom_docs",
        custom_css="/custom-docs.css",
        editor=True,
        parameters={"validatorUrl": "null", "docExpansion": '"none"'},
        oauth2_config={"clientId": '"fork-client"', "usePkceWithAuthorizationCodeGrant": "true"},
        host_inject=False,
    )
    assert "custom_docs" in app.blueprints
    client = app.test_client()
    html = client.get("/private/docs").get_data(as_text=True)
    assert 'url: "/private/docs/swagger.json"' in html
    assert 'docExpansion: "none"' in html
    assert 'href="/custom-docs.css"' in html
    assert "ui.initOAuth({" in html
    assert 'clientId: "fork-client"' in html
    assert "usePkceWithAuthorizationCodeGrant: true" in html
    assert "host" not in client.get("/private/docs/swagger.json").json
    editor = client.get("/private/docs/editor")
    assert editor.status_code == 200
    assert 'url: "/private/docs/swagger.json"' in editor.get_data(as_text=True)
    for asset in (
        "swagger-editor.js", "swagger-editor.css", "editor.worker.js",
        "apidom.worker.js", "asyncapi-parser.worker.js",
    ):
        assert client.get(f"/private/docs/static/editor/{asset}").status_code == 200
    redirect = client.get("/private/docs/static/oauth2-redirect.html")
    assert redirect.status_code == 200
    assert client.get("/private/docs/static/oauth2-redirect.js").status_code == 200
