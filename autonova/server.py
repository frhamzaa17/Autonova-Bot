from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .assistant import Assistant
from .config import KNOWLEDGE_PATH, LOG_PATH, TASKS_PATH, ensure_directories
from .document_ops import html_escape
from .knowledge_base import KnowledgeBase
from .llm import ollama_status
from .storage import read_json, read_logs


assistant = Assistant()


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def page() -> str:
    logs = read_logs(20)
    kb = KnowledgeBase().list()
    tasks = read_json(TASKS_PATH, [])
    llm = ollama_status()
    log_items = "".join(
        f"<tr><td>{html_escape(row['timestamp'])}</td><td>{html_escape(row['source'])}</td><td>{html_escape(row['message'][:120])}</td><td>{html_escape(row['response'][:160])}</td></tr>"
        for row in reversed(logs)
    )
    kb_items = "".join(
        f"<article><strong>{html_escape(item['title'])}</strong><span>{html_escape(item['category'])}</span><p>{html_escape(item['content'])}</p></article>"
        for item in kb[:20]
    )
    llm_text = "Ollama connected: " + html_escape(llm.get("model", "")) if llm.get("available") else "Ollama offline"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AutoNova Assistant Dashboard</title>
  <style>
    :root {{ color-scheme: light; --ink:#1d2730; --muted:#62717f; --line:#d8e0e8; --accent:#0f766e; --soft:#eef7f5; --warn:#8a5a00; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Arial, sans-serif; color:var(--ink); background:#f7f9fb; }}
    header {{ background:#ffffff; border-bottom:1px solid var(--line); padding:18px 28px; display:flex; justify-content:space-between; gap:16px; align-items:center; }}
    h1 {{ font-size:22px; margin:0; }}
    main {{ max-width:1180px; margin:0 auto; padding:24px; display:grid; gap:20px; }}
    .stats {{ display:grid; grid-template-columns:repeat(4,minmax(140px,1fr)); gap:12px; }}
    .stat, section, article {{ background:#fff; border:1px solid var(--line); border-radius:8px; }}
    .stat {{ padding:16px; }}
    .stat b {{ font-size:26px; display:block; }}
    .stat span, article span {{ color:var(--muted); font-size:13px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:start; }}
    section {{ padding:18px; }}
    h2 {{ margin:0 0 12px; font-size:17px; }}
    textarea, input {{ width:100%; border:1px solid var(--line); border-radius:6px; padding:10px; font:inherit; }}
    textarea {{ min-height:110px; resize:vertical; }}
    img.generated {{ max-width:100%; border:1px solid var(--line); border-radius:8px; margin-top:10px; }}
    button {{ background:var(--accent); color:white; border:0; border-radius:6px; padding:10px 14px; font-weight:700; cursor:pointer; }}
    form {{ display:grid; gap:10px; }}
    pre {{ white-space:pre-wrap; background:var(--soft); border:1px solid #c8e5df; padding:12px; border-radius:6px; min-height:80px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ text-align:left; border-bottom:1px solid var(--line); padding:8px; vertical-align:top; }}
    article {{ padding:12px; margin:10px 0; }}
    article p {{ margin:8px 0 0; color:#34414d; }}
    .health {{ color:var(--accent); font-weight:700; }}
    @media (max-width: 850px) {{ .grid, .stats {{ grid-template-columns:1fr; }} header {{ align-items:flex-start; flex-direction:column; }} }}
  </style>
</head>
<body>
  <header>
    <h1>AutoNova Business Assistant</h1>
    <div class="health">Local Phase 1 dashboard online | {llm_text}</div>
  </header>
  <main>
    <div class="stats">
      <div class="stat"><b>{len(kb)}</b><span>Knowledge entries</span></div>
      <div class="stat"><b>{len(logs)}</b><span>Recent interactions</span></div>
      <div class="stat"><b>{len([t for t in tasks if t.get('status') == 'open'])}</b><span>Open tasks</span></div>
      <div class="stat"><b>4</b><span>Integration reports</span></div>
    </div>
    <div class="grid">
      <section>
        <h2>Assistant Console</h2>
        <form id="ask-form">
          <textarea id="message" placeholder="Ask about a property, calculate brokerage, draft a document, or generate an image prompt."></textarea>
          <button type="submit">Send</button>
        </form>
        <pre id="answer">Waiting for a message...</pre>
        <div id="images"></div>
      </section>
      <section>
        <h2>Add Knowledge</h2>
        <form id="kb-form">
          <input id="category" placeholder="Category, e.g. property, contact, SOP">
          <input id="title" placeholder="Title">
          <textarea id="content" placeholder="Business information"></textarea>
          <button type="submit">Save Entry</button>
        </form>
      </section>
    </div>
    <div class="grid">
      <section>
        <h2>Knowledge Base</h2>
        {kb_items}
      </section>
      <section>
        <h2>Activity Logs</h2>
        <table><thead><tr><th>Time</th><th>Source</th><th>Message</th><th>Response</th></tr></thead><tbody>{log_items}</tbody></table>
      </section>
    </div>
  </main>
  <script>
    async function postJSON(url, payload) {{
      const res = await fetch(url, {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(payload) }});
      return await res.json();
    }}
    document.getElementById('ask-form').addEventListener('submit', async (event) => {{
      event.preventDefault();
      const message = document.getElementById('message').value;
      const data = await postJSON('/api/assistant', {{ message }});
      document.getElementById('answer').textContent = data.text + (data.files?.length ? '\\n\\nFiles:\\n' + data.files.join('\\n') : '');
      document.getElementById('images').innerHTML = (data.images || []).map(url => `<img class="generated" src="${{url}}" alt="Generated image">`).join('');
    }});
    document.getElementById('kb-form').addEventListener('submit', async (event) => {{
      event.preventDefault();
      const payload = {{
        category: document.getElementById('category').value,
        title: document.getElementById('title').value,
        content: document.getElementById('content').value
      }};
      await postJSON('/api/kb', payload);
      location.reload();
    }});
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/health":
            json_response(self, {"ok": True, "llm": ollama_status(), "knowledge_path": str(KNOWLEDGE_PATH), "log_path": str(LOG_PATH)})
        elif parsed.path == "/api/kb":
            query = parse_qs(parsed.query).get("q", [""])[0]
            kb = KnowledgeBase()
            json_response(self, kb.search(query) if query else kb.list())
        elif parsed.path == "/api/logs":
            json_response(self, read_logs(100))
        else:
            json_response(self, {"error": "Not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/assistant":
            result = assistant.handle(payload.get("message", ""), source="dashboard")
            json_response(self, {"text": result["text"], "files": [str(path) for path in result.get("files", [])], "images": result.get("images", [])})
        elif self.path == "/api/kb":
            entry = KnowledgeBase().add(payload.get("category", "note"), payload.get("title", ""), payload.get("content", ""), payload.get("tags", []))
            json_response(self, entry, 201)
        else:
            json_response(self, {"error": "Not found"}, 404)

    def log_message(self, format: str, *args) -> None:
        return


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    ensure_directories()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard running at http://{host}:{port}")
    server.serve_forever()
