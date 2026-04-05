/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080',
    NEXT_PUBLIC_COPILOTKIT_URL: process.env.NEXT_PUBLIC_COPILOTKIT_URL || 'http://localhost:8080/api/copilotkit',
  },
};
module.exports = nextConfig;
