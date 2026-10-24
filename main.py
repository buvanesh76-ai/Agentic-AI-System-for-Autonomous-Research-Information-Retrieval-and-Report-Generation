import io, os, re, json, uuid, base64, secrets, zipfile, logging
from pathlib import Path, PurePosixPath
from typing import Optional
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ai-project-builder")

APP_SECRET = os.getenv("SESSION_SECRET", "")
if not APP_SECRET:
    log.warning("SESSION_SECRET is unset. Set a strong random value before deployment.")

app = FastAPI(title="AI Project Builder API", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET or "dev-only-change-me", same_site="lax", https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true")
origins = [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET","POST","OPTIONS"], allow_headers=["Content-Type"])

PROJECTS = {}
MAX_UPLOAD = 10 * 1024 * 1024
MAX_FILES = 100
MAX_FILE_CHARS = 200_000
BLOCKED_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
BLOCKED_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".next"}

class AnalyzeRequest(BaseModel):
    topic: str = Field(min_length=10, max_length=30000)
    language: str = "Python + FastAPI"
    project_name: str = "ai-generated-project"

class GenerateRequest(AnalyzeRequest):
    pass

class PublishRequest(BaseModel):
    project_id: str
    mode: str = Field(pattern="^(create|existing)$")
    repo_name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=350)
    private: bool = True
    branch: str = Field(default="main", pattern=r"^[A-Za-z0-9._/-]{1,100}$")
    confirm: bool = False

def clean_project_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-_")
    return (name[:80] or "generated-project")

def safe_path(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > 240:
        raise ValueError("Invalid file path")
    path = path.replace("\\", "/")
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ("..", "") for part in p.parts):
        raise ValueError("Unsafe file path")
    if any(part in BLOCKED_DIRS for part in p.parts):
        raise ValueError("Generated files may not include dependency/build directories")
    if p.name.lower() in BLOCKED_NAMES or p.name.lower().startswith(".env."):
        raise ValueError("Credential/environment files cannot be generated or published")
    return str(p)

def filter_files(files: dict) -> dict:
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise ValueError("Invalid file collection")
    result = {}
    for path, content in files.items():
        path = safe_path(path)
        if not isinstance(content, str):
            raise ValueError("File contents must be text")
        if len(content) > MAX_FILE_CHARS:
            raise ValueError(f"File too large: {path}")
        result[path] = content
    return result

def fallback_files(topic: str, language: str, project_name: str) -> dict:
    # Explicitly a deterministic starter template, not AI generation.
    return {
      "README.md": f"# {project_name}\\n\\n## Overview\\n\\n{topic[:1500]}\\n\\n## Run locally\\n\\nThis is a starter scaffold. Configure an AI provider to generate a tailored codebase.\\n",
      ".gitignore": ".env\\n.env.*\\n!.env.example\\n__pycache__/\\n*.py[cod]\\n.venv/\\nvenv/\\nnode_modules/\\ndist/\\nbuild/\\n",
      ".env.example": "APP_ENV=development\\n",
      "requirements.txt": "fastapi>=0.115,<1.0\\nuvicorn[standard]>=0.30,<1.0\\npython-dotenv>=1.0,<2.0\\n",
      "backend/main.py": 'from fastapi import FastAPI\\n\\napp = FastAPI(title="Generated Starter")\\n\\n@app.get("/health")\\ndef health():\\n    return {"status": "ok"}\\n',
      "docs/SPECIFICATION.md": f"# Project specification\\n\\n- Requested stack: {language}\\n- Topic: {topic}\\n"
    }

async def call_ai(topic: str, language: str, project_name: str) -> dict:
    api_key = os.getenv("AI_API_KEY")
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")
    if not api_key:
        return fallback_files(topic, language, project_name)
    system = """You are a senior software engineer generating a runnable project repository.
Return ONLY valid JSON object mapping relative file paths to UTF-8 text contents, no markdown.
Include README.md, .gitignore, .env.example (placeholders only), and suitable dependency/config files.
Never include real secrets, .env files, binaries, node_modules, virtual environments, or build output.
Keep files under 200000 characters and total files at most 50. Use secure defaults and input validation.
Do not claim external services are configured unless documented as requiring credentials."""
    user = f"Project name: {project_name}\\nPreferred stack: {language}\\nRequirements:\\n{topic}\\n\\nCreate a complete small-to-medium functional project. Return JSON mapping file paths to contents."
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0.2, "messages": [{"role":"system","content":system},{"role":"user","content":user}]}
        )
    if response.status_code >= 400:
        log.error("AI provider error: %s %s", response.status_code, response.text[:500])
        raise HTTPException(502, "AI provider request failed. Check backend provider configuration and logs.")
    try:
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?\\s*|\\s*```$", "", content.strip(), flags=re.I)
        data = json.loads(content)
        return filter_files(data)
    except Exception as exc:
        log.exception("Invalid AI response")
        raise HTTPException(502, "AI provider returned an invalid project payload.") from exc

async def extract_upload(upload: UploadFile) -> str:
    name = (upload.filename or "").lower()
    data = await upload.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Upload exceeds 10 MB limit.")
    if name.endswith(".txt") or name.endswith(".md"):
        return data.decode("utf-8", errors="replace")[:30000]
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\\n".join((page.extract_text() or "") for page in reader.pages)[:30000]
        except Exception as exc:
            raise HTTPException(400, "Could not read PDF. Ensure it is a valid text-based PDF.") from exc
    if name.endswith(".docx"):
        try:
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\\n".join(p.text for p in doc.paragraphs)[:30000]
        except Exception as exc:
            raise HTTPException(400, "Could not read DOCX file.") from exc
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        # OCR is optional; keep the behavior honest if OCR is not installed.
        try:
            from PIL import Image
            import pytesseract
            img = Image.open(io.BytesIO(data))
            return pytesseract.image_to_string(img)[:30000]
        except Exception as exc:
            raise HTTPException(400, "Image OCR unavailable. Install Pillow, pytesseract, and the Tesseract OCR engine, or paste the text.") from exc
    raise HTTPException(415, "Supported uploads: PDF, DOCX, TXT, MD, PNG, JPG, JPEG, WEBP.")

@app.get("/api/health")
def health():
    return {"status":"ok", "ai_configured": bool(os.getenv("AI_API_KEY")), "github_configured": bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET"))}

@app.post("/api/projects/analyze")
async def analyze(topic: str = Form(""), language: str = Form("Python + FastAPI"), project_name: str = Form("ai-generated-project"), file: Optional[UploadFile] = File(None)):
    if file:
        extracted = await extract_upload(file)
        topic = (topic + "\\n\\nExtracted document content:\\n" + extracted).strip()
    if len(topic.strip()) < 10:
        raise HTTPException(400, "Enter at least 10 characters of requirements or upload a readable specification.")
    return {"project_name": clean_project_name(project_name), "language": language, "topic": topic[:30000], "summary": topic[:700]}

@app.post("/api/projects/generate")
async def generate(payload: GenerateRequest):
    project_name = clean_project_name(payload.project_name)
    files = await call_ai(payload.topic, payload.language, project_name)
    # Ensure standard repo metadata exists.
    files.setdefault("README.md", f"# {project_name}\\n\\nGenerated from the supplied requirements. Review and test before production use.\\n")
    files.setdefault(".gitignore", ".env\\n.env.*\\n!.env.example\\nnode_modules/\\n.venv/\\n__pycache__/\\ndist/\\nbuild/\\n")
    files.setdefault(".env.example", "# Add required variable names with placeholder values only.\\n")
    project_id = str(uuid.uuid4())
    PROJECTS[project_id] = {"id":project_id, "name":project_name, "language":payload.language, "topic":payload.topic, "files":files}
    return {"project_id":project_id, "project_name":project_name, "language":payload.language, "files":[{"path":p,"size":len(c)} for p,c in sorted(files.items())], "count":len(files), "provider_mode":"ai" if os.getenv("AI_API_KEY") else "starter-template"}

@app.get("/api/projects/{project_id}/files")
def list_files(project_id: str):
    project = PROJECTS.get(project_id)
    if not project: raise HTTPException(404, "Project not found or server restarted.")
    return {"project_id":project_id, "files":[{"path":p,"content":c,"size":len(c)} for p,c in sorted(project["files"].items())]}

@app.get("/api/projects/{project_id}/download")
def download(project_id: str):
    project = PROJECTS.get(project_id)
    if not project: raise HTTPException(404, "Project not found or server restarted.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, content in project["files"].items():
            safe = safe_path(path)
            z.writestr(f'{project["name"]}/{safe}', content)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition":f'attachment; filename="{project["name"]}.zip"'})

def github_configured():
    return bool(os.getenv("GITHUB_CLIENT_ID") and os.getenv("GITHUB_CLIENT_SECRET") and os.getenv("GITHUB_REDIRECT_URI"))

@app.get("/api/github/login")
def github_login(request: Request):
    if not github_configured(): raise HTTPException(503, "Configure GitHub OAuth credentials in backend .env first.")
    state = secrets.token_urlsafe(32)
    request.session["github_oauth_state"] = state
    params = {"client_id":os.getenv("GITHUB_CLIENT_ID"),"redirect_uri":os.getenv("GITHUB_REDIRECT_URI"),"scope":"repo","state":state}
    from urllib.parse import urlencode
    return RedirectResponse("https://github.com/login/oauth/authorize?"+urlencode(params))

@app.get("/api/github/callback")
async def github_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error: raise HTTPException(400, "GitHub authorization was cancelled or denied.")
    expected = request.session.pop("github_oauth_state", None)
    if not expected or not secrets.compare_digest(expected, state): raise HTTPException(400, "Invalid OAuth state. Start GitHub connection again.")
    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post("https://github.com/login/oauth/access_token", headers={"Accept":"application/json"}, json={"client_id":os.getenv("GITHUB_CLIENT_ID"),"client_secret":os.getenv("GITHUB_CLIENT_SECRET"),"code":code,"redirect_uri":os.getenv("GITHUB_REDIRECT_URI")})
        if token_resp.status_code >= 400: raise HTTPException(502, "GitHub token exchange failed.")
        token = token_resp.json().get("access_token")
        if not token: raise HTTPException(502, "GitHub did not return an access token.")
        user_resp = await client.get("https://api.github.com/user", headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
        if user_resp.status_code >= 400: raise HTTPException(502, "Could not read GitHub account.")
        user = user_resp.json()
    request.session["github_token"] = token
    request.session["github_user"] = {"login":user.get("login"),"id":user.get("id")}
    return RedirectResponse(os.getenv("FRONTEND_URL", "http://localhost:5173") + "?github=connected")

@app.get("/api/github/status")
def github_status(request: Request):
    return {"connected": bool(request.session.get("github_token")), "user":request.session.get("github_user")}

@app.post("/api/github/logout")
def github_logout(request: Request):
    request.session.pop("github_token", None); request.session.pop("github_user", None)
    return {"connected":False}

@app.get("/api/github/repositories")
async def repositories(request: Request):
    token = request.session.get("github_token")
    if not token: raise HTTPException(401, "Connect GitHub first.")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://api.github.com/user/repos", params={"per_page":100,"sort":"updated","affiliation":"owner,collaborator"}, headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    if r.status_code == 403: raise HTTPException(429, "GitHub API rate limit or permission error.")
    if r.status_code >= 400: raise HTTPException(r.status_code, "GitHub repository listing failed.")
    return [{"full_name":x["full_name"],"name":x["name"],"private":x["private"],"default_branch":x.get("default_branch") or "main","html_url":x["html_url"]} for x in r.json()]

@app.post("/api/github/publish")
async def publish(payload: PublishRequest, request: Request):
    if not payload.confirm: raise HTTPException(400, "Explicit publish confirmation is required.")
    token = request.session.get("github_token")
    if not token: raise HTTPException(401, "Connect GitHub first.")
    project = PROJECTS.get(payload.project_id)
    if not project: raise HTTPException(404, "Project not found.")
    files = filter_files(project["files"])
    headers = {"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    async with httpx.AsyncClient(timeout=60) as client:
        if payload.mode == "create":
            owner = request.session.get("github_user",{}).get("login")
            if not owner: raise HTTPException(401, "GitHub identity is missing. Reconnect.")
            r = await client.post("https://api.github.com/user/repos", headers=headers, json={"name":payload.repo_name,"description":payload.description,"private":payload.private,"auto_init":True})
            if r.status_code == 422: raise HTTPException(409, "Repository name conflict or invalid repository settings.")
            if r.status_code == 403: raise HTTPException(403, "GitHub denied repository creation. Check OAuth app permissions and account policy.")
            if r.status_code >= 400: raise HTTPException(r.status_code, f"Repository creation failed: {r.text[:300]}")
            repo = r.json()
        else:
            owner, sep, repo_name = payload.repo_name.partition("/")
            if not sep:
                owner = request.session.get("github_user",{}).get("login")
                repo_name = payload.repo_name
            if not owner or not repo_name: raise HTTPException(400, "Use repository name or owner/repository.")
            r = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}", headers=headers)
            if r.status_code == 404: raise HTTPException(404, "Repository not found or account lacks access.")
            if r.status_code >= 400: raise HTTPException(r.status_code, "Could not access target repository.")
            repo = r.json()
        owner, repo_name = repo["owner"]["login"], repo["name"]
        branch = payload.branch or repo.get("default_branch") or "main"
        # Create branch if needed; for new repos use default branch if user left "main".
        br = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}/branches/{branch}", headers=headers)
        if br.status_code == 404:
            default_branch = repo.get("default_branch") or "main"
            default_resp = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}/branches/{default_branch}", headers=headers)
            if default_resp.status_code >= 400: raise HTTPException(409, "Target branch does not exist and the repository default branch could not be read.")
            sha = default_resp.json()["commit"]["sha"]
            create_branch = await client.post(f"https://api.github.com/repos/{owner}/{repo_name}/git/refs", headers=headers, json={"ref":f"refs/heads/{branch}","sha":sha})
            if create_branch.status_code >= 400: raise HTTPException(409, "Could not create target branch. Check branch name and repository permissions.")
        elif br.status_code >= 400:
            raise HTTPException(br.status_code, "Could not read target branch.")
        # Git Data API: one tree + one commit, rather than many independent file commits.
        latest = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}/git/ref/heads/{branch}", headers=headers)
        if latest.status_code >= 400: raise HTTPException(latest.status_code, "Could not read branch head.")
        parent_sha = latest.json()["object"]["sha"]
        parent_commit = await client.get(f"https://api.github.com/repos/{owner}/{repo_name}/git/commits/{parent_sha}", headers=headers)
        if parent_commit.status_code >= 400: raise HTTPException(parent_commit.status_code, "Could not read parent commit.")
        base_tree = parent_commit.json()["tree"]["sha"]
        tree_items = []
        for path, content in files.items():
            blob = await client.post(f"https://api.github.com/repos/{owner}/{repo_name}/git/blobs", headers=headers, json={"content":content,"encoding":"utf-8"})
            if blob.status_code >= 400: raise HTTPException(blob.status_code, f"Could not upload {path} as Git blob.")
            tree_items.append({"path":path,"mode":"100644","type":"blob","sha":blob.json()["sha"]})
        tree = await client.post(f"https://api.github.com/repos/{owner}/{repo_name}/git/trees", headers=headers, json={"base_tree":base_tree,"tree":tree_items})
        if tree.status_code >= 400: raise HTTPException(tree.status_code, "GitHub could not create the repository tree.")
        commit = await client.post(f"https://api.github.com/repos/{owner}/{repo_name}/git/commits", headers=headers, json={"message":f"Publish generated project: {project['name']}","tree":tree.json()["sha"],"parents":[parent_sha]})
        if commit.status_code >= 400: raise HTTPException(commit.status_code, "GitHub could not create the commit.")
        update = await client.patch(f"https://api.github.com/repos/{owner}/{repo_name}/git/refs/heads/{branch}", headers=headers, json={"sha":commit.json()["sha"],"force":False})
        if update.status_code >= 400: raise HTTPException(409, "Commit was created but branch update failed. Refresh the repository and retry carefully.")
    return {"success":True,"repository_url":repo["html_url"],"branch":branch,"commit":commit.json()["sha"],"files_published":len(files)}
