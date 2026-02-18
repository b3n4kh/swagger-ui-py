#! env python
import argparse
import json
import os
import re
import shutil
import subprocess
import tarfile
import textwrap
from pathlib import Path

import requests
from djlint import Config
from djlint.reformat import formatter

parser = argparse.ArgumentParser()
parser.add_argument('--ui', action='store_true',
                    help='Enabled to update swagger ui.')
parser.add_argument('--editor', action='store_true',
                    help='Enabled to update swagger editor.')
parser.add_argument('--ui-version', type=str, default=None,
                    help='Specify the version of swagger ui, Default latest version.')
parser.add_argument('--editor-version', type=str, default=None,
                    help='Specify the version of swagger editor, Default latest version.')
parser.add_argument('--no-clean', action='store_true',
                    help='disable auto clean the temporary files.')
cmd_args = parser.parse_args()


SWAGGER_UI_REPO = 'swagger-api/swagger-ui'
SWAGGER_EDITOR_REPO = 'swagger-api/swagger-editor'


DOC_HTML_JAVASCRIPT = '''window.onload = function() {
    const ui = SwaggerUIBundle({
        {%- for key, value in parameters.items() %}
        {{ key|safe }}: {{ value|safe }},
        {%- endfor %}
    });

    {% if oauth2_config %}
    ui.initOAuth({
        {%- for key, value in oauth2_config.items() %}
        {{ key|safe }}: {{ value|safe }},
        {%- endfor %}
    });
    {% endif %}

    window.ui = ui;
};'''

EDITOR_NEXT_INDEX_HTML = textwrap.dedent('''\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{{ title }}</title>
    <link rel="stylesheet" href="./swagger-editor.css" />
  </head>
  <body>
    <div id="swagger-editor"></div>
    <script>
      const staticBaseUrl = '{{ url_prefix }}/static/';
      window.MonacoEnvironment = {
        baseUrl: `${staticBaseUrl}umd/`,
      };
    </script>
    <script src="./react.production.min.js"></script>
    <script src="./react-dom.production.min.js"></script>
    <script src="./umd/swagger-editor.js"></script>
    <script>
      const defaultEditorProps = {
        url: 'https://petstore.swagger.io/v2/swagger.json',
      };

      const mountNode = document.querySelector('#swagger-editor');
      const createEditorElement = (props = defaultEditorProps) =>
        React.createElement(SwaggerEditor, props);

      if (ReactDOM.createRoot) {
        const editorRoot = ReactDOM.createRoot(mountNode);
        editorRoot.render(createEditorElement());
        window.editor = {
          render(nextProps) {
            editorRoot.render(createEditorElement(nextProps || defaultEditorProps));
          },
        };
      } else {
        ReactDOM.render(createEditorElement(), mountNode);
        window.editor = {
          render(nextProps) {
            ReactDOM.render(createEditorElement(nextProps || defaultEditorProps), mountNode);
          },
        };
      }
    </script>
  </body>
</html>
''')


def detect_latest_release(repo):
    print('detect latest release')
    resp = requests.get(
        f'https://api.github.com/repos/{repo}/releases/latest', timeout=120
    )
    latest = json.loads(resp.text)
    tag = latest['tag_name']
    print(f'{repo} latest version is {tag}')
    return tag


def run_command(cmd, cwd, env=None):
    cmd_display = ' '.join(cmd)
    print(f'Running command: {cmd_display} (cwd={cwd})')
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def prepare_editor_distribution(swagger_editor_dir: Path):
    dist_dir = swagger_editor_dir.joinpath('dist')
    legacy_index_candidates = [
        dist_dir.joinpath('index.html'),
        swagger_editor_dir.joinpath('index.html'),
    ]
    if any(path.exists() for path in legacy_index_candidates):
        return {}

    npm_cmd = shutil.which('npm')
    if not npm_cmd:
        raise EnvironmentError('npm is required to build swagger-editor assets but was not found in PATH')

    print('swagger-editor distribution assets were not found; building them locally...')
    run_command([npm_cmd, 'ci'], cwd=swagger_editor_dir)

    build_env = os.environ.copy()
    build_env.setdefault('NODE_OPTIONS', '--max_old_space_size=4096')
    run_command([npm_cmd, 'run', 'build:bundle:umd'], cwd=swagger_editor_dir, env=build_env)

    if not dist_dir.exists():
        raise FileNotFoundError(f'Expected {dist_dir} to exist after running the build commands.')

    template_path = swagger_editor_dir.joinpath('swagger-editor-standalone.html')
    template_path.write_text(EDITOR_NEXT_INDEX_HTML, encoding='utf-8')

    extra_static = [
        (
            swagger_editor_dir.joinpath('node_modules/react/umd/react.production.min.js'),
            Path('react.production.min.js')
        ),
        (
            swagger_editor_dir.joinpath('node_modules/react-dom/umd/react-dom.production.min.js'),
            Path('react-dom.production.min.js')
        ),
    ]
    for src, _ in extra_static:
        if not src.exists():
            raise FileNotFoundError(f'Missing expected runtime dependency: {src}')

    public_files = [
        (swagger_editor_dir.joinpath('public/oauth2-redirect.html'), Path('oauth2-redirect.html')),
        (swagger_editor_dir.joinpath('public/oauth2-redirect.js'), Path('oauth2-redirect.js')),
        (swagger_editor_dir.joinpath('public/favicon-32x32.png'), Path('favicon-32x32.png')),
        (swagger_editor_dir.joinpath('public/favicon-16x16.png'), Path('favicon-16x16.png')),
    ]

    return {
        'template_path': template_path,
        'extra_static': extra_static,
        'public_files': public_files,
    }


def dist_copy(repo, dist_dir, build_context=None):
    build_context = build_context or {}
    index_html_candidates = [dist_dir.joinpath('index.html')]

    if repo == SWAGGER_UI_REPO:
        dst_path = templates_dir.joinpath('doc.html')

        # license file
        license_path = dist_dir.parent.joinpath('LICENSE')
        dst_license_path = static_dir.joinpath('LICENSE')
        if license_path.exists():
            shutil.copyfile(license_path, dst_license_path)
        print(f'copy {license_path} => {dst_license_path}')
    elif repo == SWAGGER_EDITOR_REPO:
        dst_path = templates_dir.joinpath('editor.html')
        # Older swagger-editor releases stored index.html at the repo root,
        # newer releases ship it under dist/. Try both so updates don't fail.
        index_html_candidates.insert(0, dist_dir.parent.joinpath('index.html'))
        template_override = build_context.get('template_path')
        if template_override:
            index_html_candidates.insert(0, template_override)
    else:
        raise ValueError(f'Unsupported repo: {repo}')

    index_html_path = next((candidate for candidate in index_html_candidates if candidate.exists()), None)
    if not index_html_path:
        candidates = ', '.join(str(candidate) for candidate in index_html_candidates)
        raise FileNotFoundError(f'Unable to locate index.html. Checked: {candidates}')

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(index_html_path, dst_path)
    print(f'copy {index_html_path} => {dst_path}')

    extra_static = build_context.get('extra_static', [])
    public_files = build_context.get('public_files', [])

    for path in dist_dir.glob('**/*'):
        if path.is_dir() or path.name == 'index.html':
            continue
        dst_path = static_dir.joinpath(path.relative_to(dist_dir))
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dst_path)
        print(f'copy {path} => {dst_path}')

    for src, relative_dst in extra_static + public_files:
        if not src.exists():
            continue
        dst_path = static_dir.joinpath(relative_dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst_path)
        print(f'copy {src} => {dst_path}')


def download_archive(repo, version):
    if version is None:
        version = detect_latest_release(repo)

    file_name = f'{version}.tar.gz'
    save_path = cur_dir.joinpath(file_name)

    if not (cmd_args.no_clean and save_path.exists()):
        archive_url = f'https://github.com/{repo}/archive/{file_name}'
        print(f'archive downloading: {archive_url}')
        with requests.get(archive_url, stream=True) as resp:
            assert resp.status_code == 200, resp.status_code
            with save_path.open('wb') as out:
                shutil.copyfileobj(resp.raw, out)
        print(f'archive download completed: {save_path}')

    print(f'open tarfile: {file_name}')
    tar_file = tarfile.open(save_path)
    tar_file.extractall(path=cur_dir)
    swagger_ui_dir = cur_dir.joinpath(tar_file.getnames()[0])

    build_context = {}
    if repo == SWAGGER_EDITOR_REPO:
        build_context = prepare_editor_distribution(swagger_ui_dir)

    dist_copy(repo, swagger_ui_dir.joinpath('dist'), build_context=build_context)

    if not cmd_args.no_clean:
        print(f'remove {swagger_ui_dir}')
        shutil.rmtree(swagger_ui_dir)

        print(f'remove {save_path}')
        save_path.unlink()

    print('Successed')
    return version


def replace_html_content():
    for html_path in templates_dir.glob('**/*.html'):
        print(html_path)
        with html_path.open('r') as html_file:
            html = html_file.read()

        html = re.sub(r'<title>.*</title>', '<title> {{ title }} </title>', html)
        html = re.sub(r'src="(\./dist/|\./|(?!{{))', 'src="{{ url_prefix }}/static/', html)
        html = re.sub(r'href="(\./dist/|\./|(?!{{))', 'href="{{ url_prefix }}/static/', html)
        html = re.sub(r'https://petstore.swagger.io/v[1-9]/swagger.json', '{{ config_url }}', html)

        if str(html_path).endswith('doc.html'):
            html = re.sub(r'window.onload = function\(\) {.*};$', DOC_HTML_JAVASCRIPT, html,
                          flags=re.MULTILINE | re.DOTALL)
            html = re.sub(
                r'<script .*/swagger-initializer.js".*</script>',
                f'<script>\n{DOC_HTML_JAVASCRIPT}\n</script>',
                html,
            )
            if 'href="{{ custom_css }}"' not in html:
                html = re.sub(
                    r'</head>',
                    '{% if custom_css %}<link rel="stylesheet" type="text/css" href="{{ custom_css }}" />{% endif %}</head>',
                    html
                )

        with html_path.open('w') as html_file:
            html_file.write(formatter(Config("-"), html))


def replace_readme(ui_version, editor_version):
    readme_path = cur_dir.parent.joinpath('README.md')
    readme = readme_path.read_text(encoding='utf-8')
    if ui_version:
        readme = re.sub(
            r'Swagger UI version is `.*`',
            f'Swagger UI version is `{ui_version}`',
            readme,
        )
        print(f'update swagger ui version: {ui_version}')
    if editor_version:
        readme = re.sub(
            r'Swagger Editor version is `.*`',
            f'Swagger Editor version is `{editor_version}`',
            readme,
        )
        print(f'update swagger editor version: {editor_version}')
    readme_path.write_text(readme)


if __name__ == '__main__':
    if not cmd_args.ui and not cmd_args.editor:
        raise ValueError("Either --ui or --editor")

    cur_dir = Path(__file__).resolve().parent

    static_dir = cur_dir.parent.joinpath('swagger_ui/static')
    templates_dir = cur_dir.parent.joinpath('swagger_ui/templates')

    ui_version = editor_version = None

    if cmd_args.ui:
        ui_version = download_archive(SWAGGER_UI_REPO, cmd_args.ui_version)
        replace_html_content()

    if cmd_args.editor:
        editor_version = download_archive(SWAGGER_EDITOR_REPO, cmd_args.editor_version)
        replace_html_content()
    replace_readme(ui_version, editor_version)
