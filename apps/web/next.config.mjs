/** @type {import('next').NextConfig} */
const apiUrl = process.env.NEXT_PUBLIC_API_URL || (process.env.VERCEL ? '' : 'http://localhost:8001');

if (process.env.VERCEL && !apiUrl) {
  throw new Error('Set NEXT_PUBLIC_API_URL to the deployed Signal-Sentry API URL in Vercel project settings.');
}

const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.NODE_ENV === 'development' ? '.next-dev' : '.next',
  env: {
    NEXT_PUBLIC_API_URL: apiUrl,
  },
};

export default nextConfig;
