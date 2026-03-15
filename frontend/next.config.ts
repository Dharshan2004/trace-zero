import type { NextConfig } from 'next'

// In production (Vercel) the frontend talks directly to the backend host.
// Set BACKEND_URL (server-side) on Vercel to your Railway/Fly.io backend URL.
// NEXT_PUBLIC_API_URL (client-side) must match for WebSocket connections.
const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000'

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
