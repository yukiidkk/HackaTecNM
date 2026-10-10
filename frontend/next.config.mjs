/** @type {import('next').NextConfig} */
const nextConfig = {
  // Permite llamadas al backend FastAPI en localhost:8000
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
