/** @type {import('next').NextConfig} */
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  // The browser talks to /api/* on the Next origin, which proxies to FastAPI.
  // One origin means no CORS preflight in the browser and no hard-coded host in
  // the client bundle.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/:path*` }];
  },
};
export default nextConfig;
