"""Hand-label clause headings, one line at a time, in a local web page.

    cd backend && .venv/bin/python tools/label_headings.py [files...] [--out PATH] [--port 8765]

Default files: data/test/templates/*.txt. Each file goes through ingest() (tier 1 only), so the lines shown are
exactly Document.text, the text the segmenter sees; labelled line numbers index Document.text.split("\\n").

Output, one row per file (rewritten on every save):
    {"source", "text_sha256", "n_lines", "layout", "headings": [{"line", "level", "text"}], "status", "note", "labeled_at"}
status: done | skip. text_sha256 is of Document.text; if ingest changes, rows whose hash no longer matches are
flagged in the page and must be checked again.

Unlabelled files are prefilled from data/test/labels/templates_labeled.jsonl (headings_v2, level 1, matched by text),
or, with --prefill PATH, from rows of tools/llm_label_tree.py ({"source", "layout", "headings": [{"line", "level"}]}).
Levels: 1 clause (Điều), 2 its first numbered subdivision (khoản). Anything deeper stays inside its level-2 unit;
level-3 marks saved before that decision are still shown (green) but can no longer be set.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ["STRUCTURE_LLM"] = "off"

from application.modules.ingestion.ingest import IngestError, ingest  # noqa: E402
from application.modules.ingestion.text import clean  # noqa: E402

DATA = BACKEND.parent / "data" / "test"
DEFAULT_OUT = DATA / "labels" / "headings_gold.jsonl"
PREFILL = DATA / "labels" / "templates_labeled.jsonl"
LAYOUTS = ["dieu_N", "dieu_roman", "roman", "numbered", "titled", "freeform"]

_lock = threading.Lock()
_cache: dict[str, dict] = {}


def load_doc(path: Path) -> dict:
    if path.name not in _cache:
        try:
            doc = ingest(path)
            text = doc.text
            tier1 = [{"line": text.count("\n", 0, c.char_start), "label": c.label} for c in doc.structure.clauses]
            _cache[path.name] = {"text": text, "tier1": tier1, "tier1_layout": doc.structure.layout,
                                 "warnings": doc.warnings, "error": None}
        except IngestError as e:
            _cache[path.name] = {"text": "", "tier1": [], "tier1_layout": None, "warnings": [], "error": str(e)}
    return _cache[path.name]


def read_rows(out: Path) -> dict[str, dict]:
    if not out.exists():
        return {}
    return {r["source"]: r for r in map(json.loads, out.read_text(encoding="utf-8").splitlines()) if r}


def write_rows(out: Path, rows: dict[str, dict], order: list[str]) -> None:
    rank = {name: i for i, name in enumerate(order)}
    tmp = out.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for name in sorted(rows, key=lambda n: (rank.get(n, len(rank)), n)):
            f.write(json.dumps(rows[name], ensure_ascii=False) + "\n")
    tmp.replace(out)


def prefill_rows(path: Path | None = None) -> dict[str, dict]:
    path = path or PREFILL
    if not path.exists():
        return {}
    return {r["source"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}


def prefill_for(name: str, lines: list[str], old: dict | None) -> dict | None:
    """Map old headings_v2 onto the clean lines by text, searching forward from the previous match.
    Rows from llm_label_tree.py already carry line numbers into this text and are passed through."""
    if not old:
        return None
    if "headings_v2" not in old:
        return {"layout": old["layout"], "headings": [{**h, "text": lines[h["line"]]} for h in old["headings"]],
                "missed": 0, "from": "llm", "description": old.get("description"), "confidence": old.get("confidence")}
    keys = [l.strip() for l in lines]
    heads, pos = [], 0
    for h in old.get("headings_v2", []):
        first = clean(h["text"].split(" / ")[0]).strip()[:40]
        if not first:
            continue
        hit = next((i for i in range(pos, len(keys)) if keys[i].startswith(first)), None)
        if hit is None:
            hit = next((i for i in range(len(keys)) if keys[i].startswith(first)), None)
        if hit is not None:
            heads.append({"line": hit, "level": 1, "text": lines[hit]})
            pos = hit + 1
    layout = old.get("layout_v2") or old.get("layout")
    return {"layout": layout if layout in LAYOUTS else "freeform", "headings": heads,
            "missed": len(old.get("headings_v2", [])) - len(heads)}


def make_handler(files: list[Path], out: Path, prefill: Path | None = None):
    by_name = {p.name: p for p in files}
    order = [p.name for p in files]
    old = prefill_rows(prefill)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def js(self, obj, code: int = 200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode())

        def do_GET(self):
            if self.path == "/":
                return self.send(200, PAGE.encode(), "text/html; charset=utf-8")
            if self.path == "/api/docs":
                rows = read_rows(out)
                return self.js({"out": str(out), "layouts": LAYOUTS, "docs": [
                    {"name": n, "status": rows[n]["status"] if n in rows else ("prefill" if n in old else "")}
                    for n in order]})
            if self.path.startswith("/api/doc/"):
                name = self.path[len("/api/doc/"):]
                from urllib.parse import unquote
                name = unquote(name)
                if name not in by_name:
                    return self.js({"error": "unknown file"}, 404)
                d = load_doc(by_name[name])
                lines = d["text"].split("\n")
                sha = hashlib.sha256(d["text"].encode()).hexdigest()
                saved = read_rows(out).get(name)
                return self.js({"name": name, "lines": lines, "sha256": sha, "error": d["error"],
                                "warnings": d["warnings"], "tier1": d["tier1"], "tier1_layout": d["tier1_layout"],
                                "saved": saved, "stale": bool(saved and saved["text_sha256"] != sha),
                                "prefill": None if saved else prefill_for(name, lines, old.get(name))})
            self.js({"error": "not found"}, 404)

        def do_POST(self):
            if not self.path.startswith("/api/doc/"):
                return self.js({"error": "not found"}, 404)
            from urllib.parse import unquote
            name = unquote(self.path[len("/api/doc/"):])
            if name not in by_name:
                return self.js({"error": "unknown file"}, 404)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            d = load_doc(by_name[name])
            lines = d["text"].split("\n")
            heads = sorted(({"line": int(h["line"]), "level": int(h["level"]), "text": lines[int(h["line"])]}
                            for h in body["headings"] if 0 <= int(h["line"]) < len(lines)), key=lambda h: h["line"])
            row = {"source": name, "text_sha256": hashlib.sha256(d["text"].encode()).hexdigest(),
                   "n_lines": len(lines), "layout": body["layout"], "headings": heads,
                   "status": body["status"], "note": body.get("note", ""),
                   "labeled_at": datetime.datetime.now().isoformat(timespec="seconds")}
            with _lock:
                rows = read_rows(out)
                rows[name] = row
                write_rows(out, rows, order)
            self.js({"ok": True, "row": row})

    return H


PAGE = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Heading labeler</title>
<style>
:root{--bg:#fbfbfa;--panel:#f1f0ed;--fg:#1d1d1b;--mute:#76746f;--line:#e2e0db;--h1:#fde7b0;--h1b:#c98a00;--h2:#dbe9fb;--h2b:#3b73c4;
--h3:#e3f3e1;--h3b:#3d8b3a;--cur:#ece9ff;--t1:#2e8b57;--bad:#c0392b;--btn:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#1b1b1a;--panel:#242423;--fg:#e8e6e1;--mute:#9a978f;--line:#34332f;--h1:#4a3a10;
--h1b:#e0a92a;--h2:#1c3350;--h2b:#6fa0e6;--h3:#1e3a1f;--h3b:#6cc068;--cur:#2e2a4a;--t1:#5cc58a;--bad:#ff7a6b;--btn:#2c2c2a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;
display:grid;grid-template-columns:230px 1fr;height:100vh;overflow:hidden}
#side{background:var(--panel);border-right:1px solid var(--line);overflow:auto;padding:8px}
#side input{width:100%;padding:5px 7px;margin-bottom:6px;background:var(--btn);color:var(--fg);border:1px solid var(--line);border-radius:5px}
.d{padding:3px 6px;border-radius:4px;cursor:pointer;display:flex;justify-content:space-between;gap:6px;font-size:13px}
.d:hover{background:var(--line)}.d.on{background:var(--cur);font-weight:600}.d .s{color:var(--mute);font-size:11px}
.s.done{color:var(--t1)}.s.skip{color:var(--bad)}
#main{display:flex;flex-direction:column;overflow:hidden}
#bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);background:var(--panel)}
#bar b{font-size:15px}#bar select,#bar input,#bar button{background:var(--btn);color:var(--fg);border:1px solid var(--line);border-radius:5px;padding:4px 8px;font:inherit}
#bar button{cursor:pointer}#bar button.pri{background:var(--h1b);color:#fff;border-color:var(--h1b)}
#note{flex:1;min-width:160px}#info{width:100%;font-size:12px;color:var(--mute)}#info .w{color:var(--bad)}
#text{overflow:auto;flex:1;padding:6px 0;font:13px/1.5 ui-monospace,monospace}
.l{display:grid;grid-template-columns:52px 34px 1fr;cursor:pointer;border-left:4px solid transparent}
.l:hover{background:var(--panel)}.l .n{color:var(--mute);text-align:right;padding-right:8px;user-select:none}
.l .t1{font-size:10px;color:var(--t1);user-select:none;padding-top:2px}.l .x{white-space:pre-wrap;word-break:break-word;padding-right:12px}
.l.h1{background:var(--h1);border-left-color:var(--h1b);font-weight:600}.l.h2{background:var(--h2);border-left-color:var(--h2b);padding-left:14px}
.l.h3{background:var(--h3);border-left-color:var(--h3b);padding-left:28px}
.l.cur{outline:2px solid var(--h2b);outline-offset:-2px}.l.empty .x::after{content:"·";color:var(--line)}
.miss .t1{color:var(--bad)}
#help{font-size:12px;color:var(--mute)}kbd{border:1px solid var(--line);border-radius:3px;padding:0 4px;font-size:11px}
</style></head><body>
<div id="side"><input id="filter" placeholder="filter… (e.g. done, skip, 12_)"><div id="list"></div></div>
<div id="main">
 <div id="bar">
  <b id="title">–</b>
  <select id="layout"></select>
  <label><input type="checkbox" id="showt1"> show tier 1</label>
  <input id="note" placeholder="note (quirks, why skipped…)">
  <button id="skip">Skip</button><button id="save" class="pri">Save &amp; next</button>
  <div id="info"></div>
  <div id="help">click = level 1 · shift-click = level 2 · click again = clear ·
   <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>1</kbd> <kbd>2</kbd> level <kbd>0</kbd> clear ·
   <kbd>s</kbd> save &amp; next · <kbd>n</kbd>/<kbd>p</kbd> next/prev doc · <kbd>t</kbd> tier 1</div>
 </div>
 <div id="text"></div>
</div>
<script>
const $=s=>document.querySelector(s);
let docs=[],cur=null,D=null,marks=new Map(),cursor=0,dirty=false;
let showT1=false;try{showT1=localStorage.getItem("t1")==="1"}catch(e){}
$("#showt1").checked=showT1;

async function api(p,body){const r=await fetch(p,body?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}:{});return r.json()}
async function loadList(){const r=await api("/api/docs");docs=r.docs;
 $("#layout").innerHTML=r.layouts.map(l=>`<option>${l}</option>`).join("");renderList()}
function renderList(){const f=$("#filter").value.trim().toLowerCase();
 const done=docs.filter(d=>d.status==="done"||d.status==="skip").length;
 $("#list").innerHTML=`<div class="s" style="padding:2px 6px">${done}/${docs.length} labelled</div>`+docs.filter(d=>!f||d.name.toLowerCase().includes(f)||d.status===f)
  .map(d=>`<div class="d${d.name===cur?" on":""}" data-n="${d.name}"><span>${d.name}</span><span class="s ${d.status}">${d.status==="prefill"?"·":d.status}</span></div>`).join("");
 document.querySelectorAll(".d").forEach(e=>e.onclick=()=>open(e.dataset.n))}
async function open(name){
 if(dirty&&!confirm("Unsaved changes on "+cur+". Discard?"))return;
 cur=name;D=await api("/api/doc/"+encodeURIComponent(name));marks=new Map();cursor=0;dirty=false;
 const src=D.saved||D.prefill;(src?src.headings:[]).forEach(h=>marks.set(h.line,h.level));
 $("#layout").value=src?src.layout:(D.tier1_layout||"freeform");$("#note").value=D.saved?D.saved.note:"";
 $("#title").textContent=name;
 let info=[];if(D.error)info.push(`<span class="w">ingest error: ${D.error}</span>`);
 if(D.stale)info.push(`<span class="w">text changed since this was labelled — check the line numbers</span>`);
 if(D.saved)info.push(`saved ${D.saved.status} at ${D.saved.labeled_at}`);
 else if(D.prefill&&D.prefill.from==="llm")info.push(`prefilled by the LLM (${D.prefill.confidence} confidence, not reviewed): ${esc(D.prefill.description||"")}`);
 else if(D.prefill)info.push(`prefilled from templates_labeled.jsonl (not reviewed)`+(D.prefill.missed?` — <span class="w">${D.prefill.missed} old heading(s) not found in the text</span>`:""));
 else info.push("no prefill");
 info.push(`tier 1: ${D.tier1_layout}, ${D.tier1.length} headings`);
 $("#info").innerHTML=info.join(" · ");renderText();renderList();$("#text").scrollTop=0}
function renderText(){const t1=new Set(D.tier1.map(c=>c.line));
 $("#text").innerHTML=D.lines.map((l,i)=>{const m=marks.get(i);const tt=showT1&&t1.has(i);const miss=showT1&&(t1.has(i)!==(m===1));
  return `<div class="l${m?" h"+m:""}${i===cursor?" cur":""}${l?"":" empty"}${miss?" miss":""}" data-i="${i}"><span class="n">${i}</span><span class="t1">${tt?"T1":miss&&m===1?"✗":""}</span><span class="x">${esc(l)}</span></div>`}).join("");
 document.querySelectorAll(".l").forEach(e=>e.onclick=ev=>{const i=+e.dataset.i;cursor=i;
  const want=ev.shiftKey?2:1;set(i,marks.get(i)===want?0:want)})}
function esc(s){return s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]))}
function set(i,lv){if(lv)marks.set(i,lv);else marks.delete(i);dirty=true;renderText()}
async function save(status){if(!D)return;
 const headings=[...marks].map(([line,level])=>({line,level}));
 const r=await api("/api/doc/"+encodeURIComponent(cur),{layout:$("#layout").value,headings,status,note:$("#note").value});
 if(r.ok){dirty=false;const d=docs.find(d=>d.name===cur);d.status=status;step(1)}}
function step(k){const i=docs.findIndex(d=>d.name===cur);const n=docs[i+k];if(n)open(n.name);else renderList()}
function move(k){cursor=Math.max(0,Math.min(D.lines.length-1,cursor+k));renderText();
 document.querySelector(`.l[data-i="${cursor}"]`)?.scrollIntoView({block:"nearest"})}
$("#save").onclick=()=>save("done");$("#skip").onclick=()=>save("skip");
$("#filter").oninput=renderList;$("#layout").onchange=()=>dirty=true;$("#note").oninput=()=>dirty=true;
$("#showt1").onchange=e=>{showT1=e.target.checked;try{localStorage.setItem("t1",showT1?"1":"0")}catch(e){}if(D)renderText()};
document.addEventListener("keydown",e=>{if(!D||e.target.matches("input,select")||e.ctrlKey||e.metaKey||e.altKey)return;
 const k=e.key;if(k==="j"||k==="ArrowDown"){move(1)}else if(k==="k"||k==="ArrowUp"){move(-1)}
 else if(k==="1"){set(cursor,1)}else if(k==="2"){set(cursor,2)}else if(k==="0"||k==="x"){set(cursor,0)}
 else if(k==="s"){save("done")}else if(k==="n"){step(1)}else if(k==="p"){step(-1)}
 else if(k==="t"){$("#showt1").click()}else return;e.preventDefault()});
window.onbeforeunload=()=>dirty?true:undefined;
loadList().then(()=>{const first=docs.find(d=>d.status!=="done"&&d.status!=="skip")||docs[0];if(first)open(first.name)});
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--prefill", type=Path, help="rows from tools/llm_label_tree.py instead of templates_labeled.jsonl")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from other machines (no auth)")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    paths = a.files or glob.glob(str(DATA / "templates" / "*.txt"))
    files = sorted((Path(p) for p in paths),
                   key=lambda p: (int(p.name.split("_")[0]) if p.name.split("_")[0].isdigit() else 10**9, p.name))
    srv = ThreadingHTTPServer((a.host, a.port), make_handler(files, a.out, a.prefill))
    print(f"{len(files)} files -> {a.out}\nhttp://{a.host}:{a.port}/", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
