import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import { Sparkles, Github, Download, FileCode2, Folder, Upload, CheckCircle2, AlertCircle, LoaderCircle, Code2, ShieldCheck, ExternalLink, RefreshCw } from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
async function request(path, options={}) {
  const res = await fetch(API+path, {credentials:'include', ...options});
  const data = await res.json().catch(()=>({detail:'Unexpected server response'}));
  if(!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}
function App(){
  const [topic,setTopic]=useState('');
  const [projectName,setProjectName]=useState('research-agent');
  const [language,setLanguage]=useState('Python + FastAPI');
  const [file,setFile]=useState(null);
  const [project,setProject]=useState(null);
  const [files,setFiles]=useState([]);
  const [selected,setSelected]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');
  const [github,setGithub]=useState({connected:false,user:null});
  const [repos,setRepos]=useState([]);
  const [mode,setMode]=useState('create');
  const [repoName,setRepoName]=useState('research-agent');
  const [description,setDescription]=useState('Generated with AI Project Builder');
  const [privateRepo,setPrivateRepo]=useState(true);
  const [branch,setBranch]=useState('main');
  const [showPublish,setShowPublish]=useState(false);
  const [health,setHealth]=useState(null);
  const [publishResult,setPublishResult]=useState(null);
  const current=files.find(f=>f.path===selected);
  useEffect(()=>{ request('/api/health').then(setHealth).catch(()=>setHealth({status:'offline'})); refreshGithub(); const params=new URLSearchParams(location.search); if(params.get('github')==='connected'){setMessage('GitHub connected successfully.');history.replaceState({},'',location.pathname)} },[]);
  async function refreshGithub(){try{const g=await request('/api/github/status');setGithub(g);if(g.connected){const r=await request('/api/github/repositories');setRepos(r)}}catch{}}
  async function generate(e){
    e?.preventDefault();setBusy(true);setError('');setMessage('Preparing project specification…');setProject(null);setFiles([]);setPublishResult(null);
    try{
      let finalTopic=topic;
      if(file){const fd=new FormData();fd.append('topic',topic);fd.append('language',language);fd.append('project_name',projectName);fd.append('file',file);const a=await request('/api/projects/analyze',{method:'POST',body:fd});finalTopic=a.topic;setTopic(finalTopic)}
      if(finalTopic.trim().length<10) throw new Error('Enter at least 10 characters of project requirements, or upload a specification.');
      setMessage('Generating files…');
      const p=await request('/api/projects/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:finalTopic,language,project_name:projectName})});
      const detail=await request(`/api/projects/${p.project_id}/files`);
      setProject(p);setFiles(detail.files);setSelected(detail.files[0]?.path||'');setRepoName(p.project_name);setMessage(`${p.count} files generated${p.provider_mode==='starter-template'?' using the starter template (AI key not configured)':''}. Review before use.`);
    }catch(err){setError(err.message);setMessage('')}finally{setBusy(false)}
  }
  async function connectGithub(){try{const r=await request('/api/github/login');location.href=r.url||API+'/api/github/login'}catch(e){setError(e.message)}}
  async function publish(){
    if(!project)return;setBusy(true);setError('');setMessage('Publishing files to GitHub…');setPublishResult(null);
    try{const result=await request('/api/github/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:project.project_id,mode,repo_name:repoName,description,private:privateRepo,branch,confirm:true})});setPublishResult(result);setMessage('GitHub confirmed the commit. Publishing completed.');}
    catch(e){setError(e.message);setMessage('')}finally{setBusy(false)}
  }
  const tree=useMemo(()=>files.map(f=>({...f,folder:f.path.includes('/')?f.path.split('/').slice(0,-1).join('/'):''})),[files]);
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-icon"><Sparkles size={20}/></div><div><b>AI Project Builder</b><small>Autonomous project studio</small></div></div>
      <div className="nav-label">WORKSPACE</div><a className="nav active"><Code2 size={17}/> Project generator</a><a className="nav" href="#files"><Folder size={17}/> Files & preview</a><a className="nav" href="#publish"><Github size={17}/> GitHub publishing</a>
      <div className="side-card"><ShieldCheck size={18}/><b>Security first</b><p>Secrets stay on the backend. Review generated code before running or publishing.</p></div>
      <div className="sidebar-bottom"><span className={`dot ${health?.status==='ok'?'green':''}`}></span>{health?.status==='ok'?'API connected':'Checking API'}<small>Local development workspace</small></div>
    </aside>
    <main className="main">
      <header className="topbar"><div><span className="eyebrow">BUILD • REVIEW • SHIP</span><h1>Turn an idea into a codebase.</h1><p>Describe your project. Generate files. Download a ZIP or publish to GitHub.</p></div><div className="top-actions"><span className="status-pill"><span className={`dot ${health?.status==='ok'?'green':''}`}></span>{health?.status==='ok'?'Backend online':'Backend unavailable'}</span></div></header>
      {(message||error)&&<div className={`notice ${error?'error':''}`}>{error?<AlertCircle size={18}/>:<CheckCircle2 size={18}/>}<span>{error||message}</span></div>}
      <section className="panel input-panel"><div className="section-head"><div className="section-icon"><Sparkles size={19}/></div><div><h2>01 / Project specification</h2><p>Be precise about features, users, data, and integrations.</p></div></div>
        <form onSubmit={generate}>
          <label htmlFor="topic">What should the application do?</label><textarea id="topic" value={topic} onChange={e=>setTopic(e.target.value)} placeholder="Example: Build a research assistant that accepts a question, searches approved sources, summarizes evidence with citations, and exports a Markdown report. Use React, FastAPI, SQLite, and a configurable AI provider. Include tests and setup instructions." rows="6"/>
          <div className="form-row"><div className="field"><label>Project folder / name</label><input value={projectName} onChange={e=>setProjectName(e.target.value)} maxLength="80" required/></div><div className="field"><label>Preferred stack</label><select value={language} onChange={e=>setLanguage(e.target.value)}><option>Python + FastAPI</option><option>React + Node.js + Express</option><option>React + FastAPI</option><option>Python + Flask</option><option>HTML + CSS + JavaScript</option><option>Java + Spring Boot</option><option>Full-stack TypeScript</option></select></div></div>
          <div className="upload-row"><label className="upload-box"><Upload size={18}/><span><b>{file?file.name:'Upload specification'}</b><small>PDF, DOCX, TXT, Markdown or image • max 10 MB</small></span><input type="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp" onChange={e=>setFile(e.target.files?.[0]||null)}/></label><button className="primary" type="submit" disabled={busy}>{busy?<LoaderCircle className="spin" size={18}/>:<Sparkles size={18}/>} {busy?'Working…':'Generate project'}</button></div>
          <p className="hint">AI generation requires a server-side AI_API_KEY. Without it, the backend returns a clearly labeled starter scaffold.</p>
        </form>
      </section>
      <section className="stats-grid"><div className="stat"><span>GENERATED FILES</span><strong>{files.length||'—'}</strong><small>Code and configuration</small></div><div className="stat"><span>AI PROVIDER</span><strong className="stat-small">{health?.ai_configured?'Configured':'Not configured'}</strong><small>{health?.ai_configured?'Server-side API enabled':'Starter template mode'}</small></div><div className="stat"><span>GITHUB</span><strong className="stat-small">{github.connected?github.user?.login:'Not connected'}</strong><small>{github.connected?'Authorization active':'OAuth authorization required'}</small></div></section>
      <section className="panel file-panel" id="files"><div className="section-head"><div className="section-icon"><FileCode2 size={19}/></div><div><h2>02 / Generated workspace</h2><p>{project?`${project.project_name} · ${files.length} files`:'Your generated folder tree and source preview appear here.'}</p></div><div className="head-actions"><button className="secondary" disabled={!project||busy} onClick={()=>window.open(`${API}/api/projects/${project.project_id}/download`,'_blank')}><Download size={16}/> Download ZIP</button></div></div>
        {files.length?<div className="explorer"><div className="file-list"><div className="file-list-title"><Folder size={15}/> PROJECT FILES <span>{files.length}</span></div>{tree.map(f=><button key={f.path} className={`file-item ${selected===f.path?'selected':''}`} onClick={()=>setSelected(f.path)}><FileCode2 size={15}/><span>{f.path}</span></button>)}</div><div className="code-area"><div className="code-title"><span><i className="code-dot"></i><i className="code-dot"></i><i className="code-dot"></i></span><b>{current?.path||'Select a file'}</b><button className="copy" onClick={()=>current&&navigator.clipboard.writeText(current.content)}>Copy</button></div><pre><code>{current?.content||'Select a file from the explorer.'}</code></pre></div></div>:<div className="empty"><div className="empty-icon"><Code2 size={26}/></div><b>No project generated yet</b><p>Enter your requirements above and select Generate project to populate the workspace.</p></div>}
      </section>
      <section className="panel publish-panel" id="publish"><div className="section-head"><div className="section-icon github-icon"><Github size={19}/></div><div><h2>03 / Publish to GitHub</h2><p>Review the destination and confirm before the backend creates a commit.</p></div><div className="head-actions">{github.connected?<span className="connected"><CheckCircle2 size={15}/> Connected as {github.user?.login}</span>:<button className="secondary" onClick={()=>location.href=API+'/api/github/login'}><Github size={16}/> Connect GitHub</button>}</div></div>
        {!github.connected?<div className="github-callout"><Github size={25}/><div><b>Authorize with GitHub OAuth</b><p>Credentials are handled server-side. Configure a GitHub OAuth App in backend/.env to enable this workflow.</p></div></div>:<div className="publish-form">
          <div className="mode-switch"><button className={mode==='create'?'on':''} onClick={()=>setMode('create')}>Create new repository</button><button className={mode==='existing'?'on':''} onClick={()=>setMode('existing')}>Use existing repository</button></div>
          {mode==='existing'&&<div className="field"><label>Accessible repositories</label><select value={repoName} onChange={e=>{setRepoName(e.target.value);const r=repos.find(x=>x.full_name===e.target.value);if(r){setPrivateRepo(r.private);setBranch(r.default_branch)}}}><option value="">Choose repository…</option>{repos.map(r=><option key={r.full_name} value={r.full_name}>{r.full_name}{r.private?' · private':''}</option>)}</select></div>}
          <div className="form-row"><div className="field"><label>{mode==='create'?'Repository name':'Repository (owner/name)'}</label><input value={repoName} onChange={e=>setRepoName(e.target.value)} placeholder="my-project" required/></div><div className="field"><label>Target branch</label><input value={branch} onChange={e=>setBranch(e.target.value)} placeholder="main" required/></div></div>
          {mode==='create'&&<><div className="field"><label>Description</label><input value={description} onChange={e=>setDescription(e.target.value)} maxLength="350"/></div><label className="check"><input type="checkbox" checked={privateRepo} onChange={e=>setPrivateRepo(e.target.checked)}/> Create as a private repository</label></>}
          <div className="publish-warning"><AlertCircle size={17}/><span>Publishing writes the generated files to the selected branch. Existing paths with the same names will be replaced in the new commit. Inspect the files above first.</span></div>
          <button className="primary" disabled={!project||busy||!repoName.trim()} onClick={()=>setShowPublish(true)}><Github size={17}/> Review & publish</button>
        </div>}
        {publishResult&&<div className="publish-success"><CheckCircle2 size={20}/><div><b>Repository updated successfully</b><p>{publishResult.files_published} files committed to <code>{publishResult.branch}</code>.</p><a href={publishResult.repository_url} target="_blank" rel="noreferrer">{publishResult.repository_url} <ExternalLink size={14}/></a></div></div>}
      </section>
      <footer>AI Project Builder <span>•</span> Generated code can contain bugs. Run tests and review security before deployment.</footer>
    </main>
    {showPublish&&<div className="modal-backdrop"><div className="modal"><div className="modal-icon"><Github size={24}/></div><h2>Confirm GitHub publishing</h2><p>You are about to publish <b>{files.length} files</b> from <b>{project?.project_name}</b> to <b>{repoName}</b> on branch <b>{branch}</b>.</p><div className="review-list">{files.slice(0,8).map(f=><span key={f.path}><FileCode2 size={14}/>{f.path}</span>)}{files.length>8&&<small>and {files.length-8} more files…</small>}</div><p className="modal-warning">This action creates a commit and may replace existing files at matching paths.</p><div className="modal-actions"><button className="secondary" onClick={()=>setShowPublish(false)}>Cancel</button><button className="primary" disabled={busy} onClick={()=>{setShowPublish(false);publish()}}>{busy?'Publishing…':'Confirm and publish'}</button></div></div></div>}
  </div>
}
createRoot(document.getElementById('root')).render(<App/>);
