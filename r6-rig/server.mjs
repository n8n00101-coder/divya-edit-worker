// Static app server + /api proxy to the live Worker (Node fetch honors env proxy).
// Usage: node server.mjs <staticDir> <port>
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const DIR = process.argv[2] || "/tmp/r6-live";
const PORT = Number(process.argv[3] || 8901);
const UP = "https://divya.n8n00101.workers.dev";
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".mp3": "audio/mpeg", ".mp4": "video/mp4", ".woff2": "font/woff2", ".txt": "text/plain" };

http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, "http://x");
    if (u.pathname.startsWith("/api/")) {
      const chunks = []; for await (const c of req) chunks.push(c);
      const body = Buffer.concat(chunks);
      const headers = {};
      for (const k of ["authorization", "content-type", "accept", "accept-language"]) if (req.headers[k]) headers[k] = req.headers[k];
      const r = await fetch(UP + u.pathname + u.search, { method: req.method, headers, body: ["GET", "HEAD"].includes(req.method) ? undefined : body });
      const buf = Buffer.from(await r.arrayBuffer());
      const rh = {}; r.headers.forEach((v, k) => { if (!["content-encoding", "transfer-encoding", "connection"].includes(k)) rh[k] = v; });
      rh["content-length"] = buf.length;
      res.writeHead(r.status, rh); res.end(buf);
      console.log("[proxy]", req.method, u.pathname, "->", r.status);
      return;
    }
    let p = u.pathname === "/" ? "/index.html" : u.pathname;
    const file = join(DIR, normalize(p).replace(/^(\.\.[/\\])+/, ""));
    const data = await readFile(file);
    res.writeHead(200, { "content-type": MIME[extname(file)] || "application/octet-stream", "cache-control": "no-store" });
    res.end(data);
  } catch (e) {
    res.writeHead(404, { "content-type": "text/plain" }); res.end("nf: " + e.message);
  }
}).listen(PORT, "127.0.0.1", () => console.log("serving", DIR, "on", PORT));
