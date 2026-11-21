/**
 * Generates the owl chat's map of the site from the resume-tree node folders.
 *
 * The registry has no central list of nodes (AGENTS.md), so the Go API cannot
 * import one — this walks the same folders `vite.config.ts` walks for the
 * sitemap and writes `gateway/internal/llm/nodes.json`, which `internal/llm` embeds
 * into the system prompt. Run `npm run gen:owl-context` in resume-page/ after adding a node.
 *
 * Nodes with a `visibleWhen` are behind sign-in and are left out: the chat route
 * is public, so its prompt may only carry what a signed-out reader can open.
 * A node's dynamic children (`<path>/:slug`, e.g. the architecture solutions)
 * are listed too, because they are pages a reader can open.
 */
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'

const NODES_DIR = new URL('../src/resume/nodes', import.meta.url).pathname
// The gateway embeds this file into the system prompt, so the path leaves the
// SPA and goes into the Go module next to it.
const OUT = new URL('../../gateway/internal/llm/nodes.json', import.meta.url).pathname

/** meta.ts is a hand-written object literal, so a field read is a regex read. */
function field(source, name) {
  const single = new RegExp(`^\\s*${name}:\\s*'((?:[^'\\\\]|\\\\.)*)'`, 'm').exec(source)
  if (single) return single[1].replace(/\\'/g, "'").replace(/\\\\/g, '\\')
  const double = new RegExp(`^\\s*${name}:\\s*"((?:[^"\\\\]|\\\\.)*)"`, 'm').exec(source)
  return double ? double[1].replace(/\\"/g, '"').replace(/\\\\/g, '\\') : null
}

/** Slugs a node serves as `<path>/:slug`, read from its own solutions list. */
function slugList(dir) {
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.ts') || file.endsWith('.test.ts') || file === 'meta.ts' || file === 'node.tsx') continue
    let source = ''
    try {
      source = readFileSync(join(dir, file), 'utf8')
    } catch {
      continue
    }
    if (!source.includes('slug:')) continue
    const found = []
    for (const m of source.matchAll(/slug:\s*'([^']+)'[\s\S]*?title:\s*'([^']*)'[\s\S]*?summary:\s*'((?:[^'\\]|\\.)*)'/g)) {
      found.push({ slug: m[1], title: m[2], teaser: m[3].replace(/\\'/g, "'") })
    }
    if (found.length > 0) return found
  }
  return []
}

function collect(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const child = join(dir, entry.name)
    let meta = ''
    try {
      meta = readFileSync(join(child, 'meta.ts'), 'utf8')
    } catch {
      // not a node folder — keep walking, it may hold some
    }
    if (meta) {
      const path = '/' + relative(NODES_DIR, child).split('\\').join('/')
      // A node behind sign-in is left out: the chat route is public, so its
      // prompt may only carry what a signed-out reader can open.
      if (!meta.includes('visibleWhen')) {
        out.push({ path, title: field(meta, 'heading') ?? field(meta, 'title') ?? '', teaser: field(meta, 'teaser') ?? '' })
      }
      // A dynamic child (`<path>/:slug`) is a real page with its own title, and
      // the reader can open it; only the parent folder has a meta.ts, so it is
      // listed here from the node's own slug list.
      for (const slug of slugList(child)) {
        out.push({ path: `${path}/${slug.slug}`, title: slug.title, teaser: slug.teaser })
      }
    }
    collect(child, out)
  }
  return out
}

const root = readFileSync(join(NODES_DIR, 'meta.ts'), 'utf8')
const nodes = [
  { path: '/', title: field(root, 'heading') ?? field(root, 'title') ?? '', teaser: field(root, 'teaser') ?? '' },
  ...collect(NODES_DIR, []),
].sort((a, b) => a.path.localeCompare(b.path))

writeFileSync(OUT, JSON.stringify(nodes, null, 2) + '\n')
console.log(`owl context: ${nodes.length} public nodes -> ${OUT}`)
