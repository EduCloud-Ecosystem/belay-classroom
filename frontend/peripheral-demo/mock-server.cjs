// SPDX-License-Identifier: AGPL-3.0-only
// Local synthetic page only. No models, text input, logs or request retention.
const http = require("node:http");
const page = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mock AI · Belay demo</title><style>body{font:20px/1.6 system-ui;background:#eef1e9;color:#243c34;max-width:650px;margin:12vh auto;padding:24px}h1{line-height:1.2}</style><h1>A mock AI site.<br>No AI runs here.</h1><p>This local page is a synthetic browser-signal fixture. It accepts no prompt and generates no answer.</p><p>Return to the Belay extension tab to explore the voluntary check-in. A visit proves neither AI use nor misconduct.</p></html>`;
function start(port = 8769) {
  if (port !== 8769) throw new Error("only the declared mock port is allowed");
  const server = http.createServer((req, res) => {
    const allowed = ["GET", "HEAD"].includes(req.method) && req.headers.host === "127.0.0.1:8769";
    res.writeHead(allowed ? 200 : 405, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"});
    res.end(allowed && req.method !== "HEAD" ? page : "");
  });
  return new Promise((resolve, reject) => { server.once("error", reject); server.listen(port, "127.0.0.1", () => resolve(server)); });
}
module.exports = {start};
if (require.main === module) start().then(() => process.stdout.write("Mock page ready at http://127.0.0.1:8769 (no request logging)\n")).catch(() => { process.stderr.write("Mock page could not bind its declared loopback port.\n"); process.exitCode = 1; });
