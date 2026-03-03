# DocSync

`doc` is a Python CLI that syncs one Google Doc's tabs to local XML files and back using incremental Google Docs API patches.

## Current feature scope

- `doc pull`: materialize tabs as XML files and store sync metadata in `.docsync_state.json`.
- `doc push`: strict mode, aborts if remote revision changed since last pull.
- `doc push -f`: best-effort mode with a safe rebase policy; aborts on unsafe overlap.
- `doc push -f --dry-run`: preview operations and conflicts without writing.

## Safety model

- Strict mode never writes when revision drift is detected.
- Force mode only applies minimal incremental edits (no full-document replacement).
- Force mode aborts with conflict reports for overlapping/unsafe edits.

## Assumptions for v1

- Tabs are represented in editable XML (`.xml`) files.
- Simultaneous edits are uncommon; strict mode is default.
- Authentication uses Application Default Credentials (ADC).

## Google authentication

The CLI uses the standard Google ADC flow from `google-auth`.

You have two common options:

1. User OAuth (great for local development):

   **Important for now:** to request Docs/Drive scopes, you need your own OAuth client ID file.
   The default `gcloud auth application-default login` client can be blocked for non-Cloud scopes.
   See Google's ADC troubleshooting guidance:
   <https://docs.cloud.google.com/docs/authentication/troubleshoot-adc#access_blocked_when_using_scopes>

   Steps:

   - Create an OAuth client in Google Cloud Console (Desktop app client is fine for local dev).
   - Download the client JSON file.
   - Run:

     ```bash
     gcloud auth application-default login \
       --client-id-file=/absolute/path/to/client_secret.json \
       --scopes="https://www.googleapis.com/auth/documents,https://www.googleapis.com/auth/drive.readonly,openid,https://www.googleapis.com/auth/userinfo.email"
     ```

   This is a temporary setup requirement until the project is reviewed/published and can use a simpler default flow.

2. Service account key (great for automation/CI):
   - Create a service account and JSON key in Google Cloud.
   - Share the target Google Doc with that service account email.
   - Point ADC to the key file via `GOOGLE_APPLICATION_CREDENTIALS`.

You can export that variable in your shell:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/absolute/path/to/service-account.json"
```

Or use a local `.env` file (loaded automatically by the CLI):

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

Required scope used by this tool: `https://www.googleapis.com/auth/documents`.

## Quickstart

1. Install:

   ```bash
   poetry install
   ```

2. Authenticate with Google APIs (Application Default Credentials).

3. Pull:

   ```bash
   poetry run doc pull <DOC_ID> --workspace . --verbose
   ```

   If you used an older Markdown-based workspace, run `pull` again to migrate files/state to XML.

4. Edit generated `.xml` files.

5. Push:

   ```bash
   poetry run doc push <DOC_ID> --workspace . --verbose
   ```

Force mode:

```bash
poetry run doc push <DOC_ID> --workspace . -f
```

For large documents, use incremental progress logs and tune batch size:

```bash
poetry run doc push <DOC_ID> --workspace . --verbose --batch-size 50
```

If you interrupt with Ctrl+C, DocSync now logs the current processing stage and stack context to `.docsync.log` by default. You can customize logging:

```bash
poetry run doc --log-file /tmp/docsync.log --log-level DEBUG push <DOC_ID> --verbose
```

## PyPI and pipx

After publishing to PyPI, users can install globally with:

```bash
pipx install docsync
```

For maintainers, build and verify locally before upload:

```bash
poetry check
poetry build
poetry run python -m twine check dist/*
```

Publishing auth options:

- Preferred: PyPI Trusted Publishing (OIDC in CI; no local token needed).
- Alternative: PyPI API token (`pypi-...`) configured for Poetry:

  ```bash
  poetry config pypi-token.pypi <YOUR_PYPI_TOKEN>
  poetry publish
  ```

Do not upload credential files (`.env`, OAuth client secrets, service account keys).
