.PHONY: format format-check whl pytest install upload

format:
	uv run ruff format swagger_ui/
	uv run isort --line-width=100 --force-single-line-imports .

format-check:
	uv run ruff check .
	uv run isort --line-width=100 --force-single-line-imports --check .

whl:
	uv build
	uv run python tools/verify_assets.py dist/*.whl

pytest:
	uv run --extra test pytest -q test/

install:
	uv sync --frozen --all-extras

upload:
	@echo 'Publish using the approved release tag workflow described in RELEASE.md.'
