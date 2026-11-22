/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: process.env.NEXT_OUTPUT_STANDALONE ? "standalone" : undefined,
  trailingSlash: false,
};

export default nextConfig;
