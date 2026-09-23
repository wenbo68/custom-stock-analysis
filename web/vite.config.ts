import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

const packageJson = JSON.parse(
  readFileSync(new URL('./package.json', import.meta.url), 'utf-8'),
) as { version?: string }
const buildTime = new Date().toISOString()

// Slimmed from the parent project: this app ships no charts/markdown/motion
// bundles, so the vendor split is just react / router / icons.
const vendorChunkByPackage: Record<string, string> = {
  react: 'vendor-react',
  'react-dom': 'vendor-react',
  scheduler: 'vendor-react',
  'react-router': 'vendor-router',
  'react-router-dom': 'vendor-router',
  'lucide-react': 'vendor-icons',
}

// The Markdown renderer for chat replies is loaded lazily (one page's
// feature); its packages must not be swept into the shared vendor
// chunk the analysis page downloads. Everything react-markdown and
// remark-gfm depend on is left to Rollup, which keeps a module used by
// one lazy chunk alone inside that chunk.
const lazyOnlyPackages = (() => {
  const seen = new Set<string>()
  const queue = ['react-markdown', 'remark-gfm']
  while (queue.length > 0) {
    const name = queue.pop() as string
    if (seen.has(name)) {
      continue
    }
    seen.add(name)
    try {
      const manifest = JSON.parse(
        readFileSync(new URL(`./node_modules/${name}/package.json`, import.meta.url), 'utf-8'),
      ) as { dependencies?: Record<string, string> }
      queue.push(...Object.keys(manifest.dependencies ?? {}))
    } catch {
      // not installed at the top level: nothing to walk
    }
  }
  seen.delete('react')
  seen.delete('react-dom')
  return seen
})()

const getVendorChunkName = (id: string): string | undefined => {
  const normalizedId = id.replace(/\\/g, '/')
  const marker = '/node_modules/'
  const markerIndex = normalizedId.lastIndexOf(marker)
  if (markerIndex === -1) {
    return undefined
  }
  const [firstSegment, secondSegment] = normalizedId
    .slice(markerIndex + marker.length)
    .split('/')
  if (!firstSegment) {
    return undefined
  }
  const packageName = firstSegment.startsWith('@')
    ? (secondSegment ? `${firstSegment}/${secondSegment}` : undefined)
    : firstSegment
  if (!packageName || lazyOnlyPackages.has(packageName)) {
    return undefined
  }
  return vendorChunkByPackage[packageName] ?? 'vendor'
}

// https://vite.dev/config/
export default defineConfig({
  define: {
    __APP_PACKAGE_VERSION__: JSON.stringify(packageJson.version ?? '0.0.0'),
    __APP_BUILD_TIME__: JSON.stringify(buildTime),
  },
  plugins: [
    tailwindcss(),
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Build straight into the repo-root static/ folder the API serves.
    outDir: path.resolve(__dirname, '../static'),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: getVendorChunkName,
      },
    },
  },
})
