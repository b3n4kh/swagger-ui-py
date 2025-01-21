from pathlib import Path

cur_dir = Path(__file__).resolve().parent

config_path = str(cur_dir.joinpath('conf/test3.yaml'))
config_content = Path(config_path).read_text()

kwargs_list = [
    {
        'url_prefix': '/api/doc',
        'config_path': config_path,
    },
    {
        'url_prefix': '/api/doc',
        'config_path': config_path,
        'editor': True,
    },
    {
        'url_prefix': '/',
        'config_path': config_path,
    },
    {
        'url_prefix': '',
        'config_path': config_path,
    },
    {
        'url_prefix': '/',
        'config_path': config_path,
        'config_rel_url': '/swagger.json',
    },
]
