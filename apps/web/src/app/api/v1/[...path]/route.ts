import type { NextRequest } from "next/server";

// Runtime proxy from the browser-facing Next.js origin to the FastAPI service.
// Keeping this in a route handler (instead of next.config rewrites) means
// API_INTERNAL_URL is read per request, not baked in at build time.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOP_BY_HOP = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

function apiTarget(): string {
  const raw =
    process.env.API_INTERNAL_URL ??
    process.env.API_PROXY_TARGET ??
    "http://localhost:8000";
  const base = /^https?:\/\//.test(raw) ? raw : `http://${raw}`;
  return base.replace(/\/$/, "");
}

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  const target = `${apiTarget()}/api/v1/${path.join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const method = request.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
      // Free Render services can cold-start in ~1 minute.
      signal: AbortSignal.timeout(120_000),
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "API_UNREACHABLE",
          message: "The API service is not reachable from the web service.",
          details: null,
          request_id: request.headers.get("x-request-id") ?? "proxy",
          retryable: true,
        },
      },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "set-cookie") responseHeaders.set(key, value);
  });

  // Preserve the session cookie exactly. getSetCookie() is available on Node 20+.
  const withCookies = upstream.headers as Headers & { getSetCookie?: () => string[] };
  const cookies = withCookies.getSetCookie?.() ?? [];
  if (cookies.length) {
    for (const cookie of cookies) responseHeaders.append("set-cookie", cookie);
  } else {
    const cookie = upstream.headers.get("set-cookie");
    if (cookie) responseHeaders.append("set-cookie", cookie);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export {
  proxy as DELETE,
  proxy as GET,
  proxy as HEAD,
  proxy as OPTIONS,
  proxy as PATCH,
  proxy as POST,
  proxy as PUT,
};
