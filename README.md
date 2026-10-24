# AI Project Builder

A React/Vite frontend and FastAPI backend for turning project requirements into a generated source tree, downloading a ZIP, and publishing a single Git commit to GitHub.

## Features

- Project specification text and PDF, DOCX, TXT, Markdown, and image upload.
- Server-side AI integration using an OpenAI-compatible Chat Completions API.
- File tree, code preview, copy-to-clipboard, ZIP download.
- GitHub OAuth login, repository listing, repository creation, branch selection, and Git Data API commit.
- Input validation, upload size limits, safe relative paths, environment-file exclusion, OAuth state checking, and explicit publish confirmation.
- Honest fallback: without `AI_API_KEY`, the app generates a clearly labeled starter scaffold rather than pretending it used AI.

## Requirements

- Python 3.10+
- Node.js 20+ recommended
- A provider API key for AI generation (optional for starter scaffold)
- A GitHub OAuth App for GitHub publishing

## Run locally

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:
- Set `SESSION_SECRET` to a random 32+ character secret.
- Set `AI_API_KEY`, `AI_BASE_URL`, and `AI_MODEL` for AI generation.
- Configure GitHub OAuth values to enable publishing.

Start the API from the `backend` directory:

```bash
uvicorn app.main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### 2. Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

If your backend runs elsewhere, create `frontend/.env` with `VITE_API_URL=http://localhost:8000` and restart Vite.

## Configure GitHub OAuth

1. In GitHub, open Settings → Developer settings → OAuth Apps → New OAuth App.
2. Set the Homepage URL to `http://localhost:5173`.
3. Set the Authorization callback URL to `http://localhost:8000/api/github/callback`.
4. Copy the client ID and client secret into `backend/.env`.
5. Restart the backend.

The app requests the `repo` OAuth scope because publishing to private repositories requires repository access. This is broader than public-only publishing. For a production deployment, consider a GitHub App with narrowly scoped Contents and Metadata permissions and repository selection.

## API routes

- `POST /api/projects/analyze` — multipart topic/specification extraction.
- `POST /api/projects/generate` — generate codebase.
- `GET /api/projects/{project_id}/files` — retrieve generated file contents.
- `GET /api/projects/{project_id}/download` — ZIP download.
- `GET /api/github/login` — start OAuth.
- `GET /api/github/callback` — validate state and exchange OAuth code.
- `GET /api/github/status` — session connection status.
- `POST /api/github/logout` — clear GitHub session.
- `GET /api/github/repositories` — list accessible repositories.
- `POST /api/github/publish` — create/update files in a single commit.
- `GET /api/health` — provider configuration status.

## Test manually

1. Start backend and frontend; check `/api/health`.
2. Generate a project with AI_API_KEY unset; verify the UI labels it starter-template mode.
3. Configure an AI key and generate again; inspect file tree and README.
4. Download ZIP; inspect archive paths and verify `.env` is absent.
5. Configure OAuth and authorize; check the GitHub username in the UI.
6. Create a private test repository and publish to `main`.
7. Publish to an existing disposable repository and verify one commit includes the files.
8. Test invalid upload types, files over 10 MB, missing project ID, missing OAuth, and repository conflicts.

## Important production hardening

This is a functional starter application, not a fully production-hardened multi-user service. Before public deployment:
- Replace in-memory `PROJECTS` storage with authenticated persistent storage and ownership checks; projects currently disappear on server restart and are not suitable for multi-worker deployment.
- Add CSRF protections for cookie-authenticated mutating endpoints, per-user rate limits, quotas, audit logs, and strict session expiration.
- Set HTTPS, `COOKIE_SECURE=true`, a strong `SESSION_SECRET`, and correct CORS/FRONTEND_URL values.
- Consider a GitHub App instead of OAuth `repo` scope; use least-privilege installation permissions.
- Add automated tests, sandbox generated-code execution, malware scanning, and dependency/license checks.
- Add OCR engine installation if image OCR is needed. Python packages alone do not install the Tesseract system binary.
- Validate generated projects by running tests in an isolated sandbox. Generated code is not guaranteed correct or safe.
- For very large projects, use background jobs and streaming progress events instead of one long request.

## Notes

Generated project code is untrusted input. Review it before running or publishing. The backend does not execute generated code.
