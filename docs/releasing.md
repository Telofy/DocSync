# Releasing to PyPI

## 1) Preflight checks

```bash
poetry install
poetry run basedpyright
poetry check
```

## 2) Build and validate artifacts

```bash
poetry build
poetry run python -m pip install twine
poetry run python -m twine check dist/*
```

## 3) Publish

Choose one auth method:

- Trusted Publishing (recommended): configure your GitHub repository on PyPI and publish from CI.
- API token: create a PyPI token and run:

  ```bash
  poetry config pypi-token.pypi <YOUR_PYPI_TOKEN>
  poetry publish
  ```

## 4) Smoke test from a clean environment

```bash
pipx install docfs-sync
doc --help
```
