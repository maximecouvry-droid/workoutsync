const isVercel = Boolean(process.env.VERCEL);

/** @type {import("next").NextConfig} */
const nextConfig = {
  async rewrites() {
    if (isVercel) return [];
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
