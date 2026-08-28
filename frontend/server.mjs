import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { extname, join, normalize } from "node:path";
import { createServer } from "node:http";

const root = join(process.cwd(), "dist");
const port = Number(process.env.PORT ?? 80);
const apiTarget = new URL(process.env.API_PROXY_TARGET ?? "http://backend:8000");

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".webp": "image/webp",
};

function resolvePath(url) {
  const pathname = decodeURIComponent(new URL(url, `http://localhost:${port}`).pathname);
  const candidate = normalize(join(root, pathname));
  return candidate.startsWith(root) ? candidate : join(root, "index.html");
}

async function fileFor(url) {
  const candidate = resolvePath(url);
  try {
    const info = await stat(candidate);
    if (info.isFile()) return candidate;
  } catch {
    // Fall through to SPA fallback.
  }
  return join(root, "index.html");
}

function proxyApi(request, response) {
  const upstreamUrl = new URL(request.url ?? "/", apiTarget);
  const headers = { ...request.headers, host: apiTarget.host };
  delete headers.connection;
  delete headers["content-length"];

  const upstreamRequest = (apiTarget.protocol === "https:" ? httpsRequest : httpRequest)(
    upstreamUrl,
    {
      method: request.method,
      headers,
    },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    },
  );

  upstreamRequest.on("error", () => {
    response.writeHead(502, { "Content-Type": "application/json; charset=utf-8" });
    response.end(JSON.stringify({ error: { code: "backend_unavailable", message: "Backend unavailable" } }));
  });

  request.pipe(upstreamRequest);
}

createServer(async (request, response) => {
  if ((request.url ?? "/").startsWith("/api/")) {
    proxyApi(request, response);
    return;
  }

  const filePath = await fileFor(request.url ?? "/");
  response.setHeader("Content-Type", contentTypes[extname(filePath)] ?? "application/octet-stream");
  createReadStream(filePath)
    .on("error", () => {
      response.writeHead(500);
      response.end("Internal Server Error");
    })
    .pipe(response);
}).listen(port, "0.0.0.0");
