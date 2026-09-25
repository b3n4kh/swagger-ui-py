"""Local browser smoke fixture; run with Python from an installed-wheel environment."""

from flask import Flask
from flask import jsonify
from flask import redirect
from flask import request

import swagger_ui
from swagger_ui import api_doc

app = Flask(__name__)
spec = {
    "openapi": "3.0.3",
    "info": {
        "title": "Bundled assets smoke test",
        "version": "1.0",
        "description": (
            "**Markdown works** <b>safe-markup</b>"
            '<img src="data:," onerror="window.swaggerSmokeXss=1">'
            "<script>window.swaggerSmokeXss=2</script>"
        ),
    },
    "paths": {
        "/hello": {
            "get": {
                "summary": "Local smoke operation",
                "responses": {"200": {"description": "OK"}},
                "security": [{"smokeOAuth": ["read"]}],
            }
        }
    },
    "components": {
        "securitySchemes": {
            "smokeOAuth": {
                "type": "oauth2",
                "flows": {
                    "authorizationCode": {
                        "authorizationUrl": "http://127.0.0.1:8765/authorize",
                        "tokenUrl": "http://127.0.0.1:8765/token",
                        "scopes": {"read": "Read smoke data"},
                    }
                },
            }
        }
    },
}
api_doc(
    app,
    config=spec,
    url_prefix="/private/docs",
    blueprint_name="custom_docs",
    editor=True,
    host_inject=False,
    parameters={
        "validatorUrl": "null",
        "docExpansion": '"none"',
        "oauth2RedirectUrl": '"http://127.0.0.1:8765/private/docs/static/oauth2-redirect.html"',
    },
    oauth2_config={
        "clientId": '"fork-smoke-client"',
        "usePkceWithAuthorizationCodeGrant": "true",
        "scopes": '"read"',
    },
)


@app.get("/hello")
def hello():
    return jsonify(message="Hello from installed wheel")


@app.get("/authorize")
def authorize():
    # Fixed loopback destination: never redirect to an untrusted request parameter.
    from urllib.parse import urlencode

    query = urlencode({"code": "smoke-code", "state": request.args["state"]})
    return redirect(f"/private/docs/static/oauth2-redirect.html?{query}")


@app.post("/token")
def token():
    assert request.form["code"] == "smoke-code"
    assert request.form["code_verifier"]
    return jsonify(access_token="local-smoke-token", token_type="Bearer", scope="read")


if __name__ == "__main__":
    print(f"Serving installed package: {swagger_ui.__file__}", flush=True)
    app.run(host="127.0.0.1", port=8765, debug=False)
