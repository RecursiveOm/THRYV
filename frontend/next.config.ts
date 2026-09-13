import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const parsed = new URL(apiUrl);
const production = process.env.NODE_ENV === "production";
if (
  parsed.username ||
  parsed.password ||
  parsed.search ||
  parsed.hash ||
  parsed.pathname !== "/"
) {
  throw new Error(
    "NEXT_PUBLIC_API_URL must be an origin without credentials, path, or query.",
  );
}
if (!["https:", "http:"].includes(parsed.protocol))
  throw new Error("Invalid API URL protocol.");
if (
  production &&
  parsed.protocol !== "https:" &&
  !["localhost", "127.0.0.1"].includes(parsed.hostname)
) {
  throw new Error("Production API connections must use HTTPS.");
}

const config: NextConfig = {
  distDir: process.env.THRYV_TEST_BUILD === "1" ? ".next-test" : ".next",
  poweredByHeader: false,
  devIndicators: false,
  turbopack: { root: process.cwd() },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(self), geolocation=()",
          },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "base-uri 'self'",
              "object-src 'none'",
              "frame-ancestors 'none'",
              "form-action 'self'",
              "img-src 'self' data:",
              "media-src 'self' blob:",
              "font-src 'self'",
              "style-src 'self' 'unsafe-inline'",
              `script-src 'self' 'unsafe-inline'${production ? "" : " 'unsafe-eval'"}`,
              `connect-src 'self' ${parsed.origin}${production ? "" : " ws://localhost:* ws://127.0.0.1:*"}`,
            ].join("; "),
          },
        ],
      },
    ];
  },
};
export default config;
