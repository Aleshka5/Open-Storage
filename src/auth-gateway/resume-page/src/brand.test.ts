import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apply, brandStaysInApp, HUB_ORIGIN, persist, readPreference, resolve, watchSystem } from './theme'

const pageRoot = process.cwd()

const colorTokens = [
  '--paper',
  '--paper-raised',
  '--surface-raised',
  '--ink',
  '--ink-muted',
  '--rule',
  '--rule-strong',
  '--accent',
  '--accent-text',
  '--chip',
  '--danger',
  '--danger-wash',
]

function readPage(path: string) {
  return readFileSync(join(pageRoot, path), 'utf8')
}

function walk(dir: string): string[] {
  const found: string[] = []
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === 'dist') continue
    const path = join(dir, name)
    if (statSync(path).isDirectory()) found.push(...walk(path))
    else if (/\.(css|ts|tsx|html|js)$/.test(name)) found.push(path)
  }
  return found
}

function ruleset(css: string, selector: string) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const found = css.match(new RegExp(`(?:^|[}\\s])${escaped}\\s*\\{([^}]*)\\}`))
  expect(found, selector).not.toBeNull()
  return found![1]
}

function expectBothFaces(block: string, selector: string) {
  expect(block, `${selector} background`).toMatch(/background(?:-color)?\s*:/)
  expect(block, `${selector} color`).toMatch(/(?<![\w-])color\s*:/)
}

function ensureMeta() {
  let meta = document.querySelector('meta[name="color-scheme"]')
  if (!meta) {
    meta = document.createElement('meta')
    meta.setAttribute('name', 'color-scheme')
    document.head.appendChild(meta)
  }
  return meta
}

function installScheme(matches: boolean) {
  let current = matches
  const listeners = new Set<() => void>()
  const media = {
    get matches() {
      return current
    },
    media: '(prefers-color-scheme: light)',
    addEventListener(_type: string, listener: () => void) {
      listeners.add(listener)
    },
    removeEventListener(_type: string, listener: () => void) {
      listeners.delete(listener)
    },
    addListener(listener: () => void) {
      listeners.add(listener)
    },
    removeListener(listener: () => void) {
      listeners.delete(listener)
    },
    emit(next: boolean) {
      current = next
      for (const listener of listeners) listener()
    },
  }
  vi.stubGlobal('matchMedia', (query: string) => {
    if (query === '(prefers-color-scheme: light)') return media
    return {
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
    }
  })
  return media
}

function headScript() {
  const html = readPage('index.html')
  const head = html.slice(html.indexOf('<head>'), html.indexOf('</head>'))
  const script = head.match(/<script>([\s\S]*?)<\/script>/)
  expect(script, 'blocking theme script').not.toBeNull()
  expect(head).not.toMatch(/<script\s/)
  return { html, head, script: script![1] }
}

type JsdomWindow = { jsdom?: { reconfigure(settings: { url: string }): void } }

/** Point `location` at one host. jsdom keeps a single document, so this is not a second origin. */
function useHost(hostname: string, protocol: 'http:' | 'https:') {
  const dom = (globalThis as JsdomWindow).jsdom
  if (!dom) throw new Error('jsdom is required to set location.hostname')
  const scheme = protocol === 'https:' ? 'https' : 'http'
  dom.reconfigure({ url: `${scheme}://${hostname}/` })
}

function spyCookie() {
  const proto = Document.prototype
  const original = Object.getOwnPropertyDescriptor(proto, 'cookie')
  if (!original?.get || !original.set) throw new Error('cookie descriptor missing')
  const writes: string[] = []
  Object.defineProperty(proto, 'cookie', {
    configurable: true,
    enumerable: original.enumerable,
    get: original.get,
    set(value: string) {
      writes.push(String(value))
      return original.set!.call(this, value)
    },
  })
  return {
    writes,
    restore() {
      Object.defineProperty(proto, 'cookie', original)
    },
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
  Reflect.deleteProperty(document, 'cookie')
})

describe('theme preference', () => {
  it('paints dark for a missing, unknown, or unreadable preference', () => {
    ensureMeta()
    installScheme(true)
    document.cookie = 'theme.preference=; Path=/; Max-Age=0'
    Storage.prototype.setItem.call(localStorage, 'theme.preference', 'light')
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    expect(readPreference()).toBe('dark')
    apply(readPreference())
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')

    document.cookie = 'theme.preference=sepia; Path=/'
    expect(readPreference()).toBe('dark')
    apply(readPreference())
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')).toBe('dark')
    expect(localStorage.getItem('theme.preference')).toBe('light')

    const original = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie')
    Object.defineProperty(document, 'cookie', {
      configurable: true,
      get() {
        throw new Error('blocked')
      },
      set() {
        throw new Error('blocked')
      },
    })
    expect(readPreference()).toBe('dark')
    expect(() => apply(readPreference())).not.toThrow()
    expect(() => persist('light')).not.toThrow()
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
    expect(setItem).not.toHaveBeenCalled()
    expect(localStorage.getItem('theme.preference')).toBe('light')
    if (original) Object.defineProperty(Document.prototype, 'cookie', original)
  })

  it('follows prefers-color-scheme only while the preference is system', () => {
    ensureMeta()
    const media = installScheme(false)
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    document.cookie = 'unrelated=1'
    document.cookie = 'theme.preference=system; Path=/'
    expect(readPreference()).toBe('system')
    expect(resolve(readPreference())).toBe('dark')
    const stop = watchSystem(() => apply(readPreference()))

    media.emit(true)
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
    expect(document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')).toBe('light')

    media.emit(false)
    expect(document.documentElement.dataset.theme).toBe('dark')

    persist('dark')
    media.emit(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.cookie).toContain('theme.preference=dark')
    expect(setItem).not.toHaveBeenCalled()
    expect(localStorage.getItem('theme.preference')).toBeNull()
    stop()
  })

  it('writes Domain=.filenkov.store on the hub and on storage', () => {
    const { writes, restore } = spyCookie()
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    try {
      useHost('filenkov.store', 'https:')
      expect(location.hostname).toBe('filenkov.store')
      expect(location.protocol).toBe('https:')
      persist('light')
      expect(writes).toEqual([
        'theme.preference=light; Path=/; SameSite=Lax; Secure; Domain=.filenkov.store',
      ])
      expect(setItem).not.toHaveBeenCalled()
      expect(readPreference()).toBe('light')

      useHost('storage.filenkov.store', 'https:')
      expect(location.hostname).toBe('storage.filenkov.store')
      expect(readPreference()).toBe('light')
      writes.length = 0
      persist('dark')
      expect(writes).toEqual([
        'theme.preference=dark; Path=/; SameSite=Lax; Secure; Domain=.filenkov.store',
      ])

      useHost('filenkov.store', 'https:')
      expect(readPreference()).toBe('dark')

      writes.length = 0
      useHost('filenkov.store', 'http:')
      persist('system')
      expect(writes).toEqual(['theme.preference=system; Path=/; SameSite=Lax; Domain=.filenkov.store'])

      writes.length = 0
      useHost('localhost', 'http:')
      expect(location.hostname).toBe('localhost')
      persist('light')
      expect(writes).toEqual(['theme.preference=light; Path=/; SameSite=Lax'])
      expect(setItem).not.toHaveBeenCalled()
    } finally {
      restore()
    }
  })

  it('runs readPreference, resolve, and apply from a blocking head script', () => {
    const { html, script } = headScript()
    expect(html).toMatch(/<html[^>]*data-theme="dark"[^>]*color-scheme:\s*dark/)
    expect(html).toContain('<meta name="color-scheme" content="dark"')
    expect(script).toContain('function readPreference()')
    expect(script).toContain('function resolve(preference)')
    expect(script).toContain('function apply(preference)')
    expect(script).toContain('apply(readPreference())')
    expect(script).toContain("matchMedia('(prefers-color-scheme: light)')")
    expect(script).toContain('document.cookie')
    expect(script).not.toContain('localStorage')
    expect(script).not.toContain('type="module"')

    ensureMeta()
    const media = installScheme(true)
    Storage.prototype.setItem.call(localStorage, 'theme.preference', 'light')
    document.cookie = 'theme.preference=nope'
    new Function(script)()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')

    document.cookie = 'theme.preference=system'
    new Function(script)()
    expect(document.documentElement.dataset.theme).toBe('light')
    media.emit(false)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(document.querySelector('meta[name="color-scheme"]')?.getAttribute('content')).toBe('dark')

    document.cookie = 'theme.preference=light'
    new Function(script)()
    media.emit(false)
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('theme.preference')).toBe('light')
  })

  it('keeps the wordmark in-app only on the hub origin', () => {
    expect(brandStaysInApp(HUB_ORIGIN)).toBe(true)
    expect(brandStaysInApp('http://127.0.0.1:4173')).toBe(false)
  })

  it('does not store a session in localStorage', () => {
    const writes: string[] = []
    for (const file of walk(pageRoot)) {
      const text = readFileSync(file, 'utf8')
      for (const write of text.match(/localStorage\.setItem\([^)]*\)/g) ?? []) writes.push(`${file} ${write}`)
    }
    expect(writes).toEqual([])
    expect(readPage('src/theme.ts')).not.toContain('localStorage')
  })
})

describe('theme faces', () => {
  const theme = readPage('src/styles/theme.css')
  const root = theme.match(/:root\s*\{([^}]*)\}/)?.[1] ?? ''
  const light = theme.match(/\[data-theme="light"\]\s*\{([^}]*)\}/)?.[1] ?? ''

  it('keeps both palettes, the motion tokens, and both faces', () => {
    expect(root).not.toBe('')
    expect(light).not.toBe('')
    for (const token of colorTokens) {
      expect(root, token).toMatch(new RegExp(`${token}\\s*:`))
      expect(light, token).toMatch(new RegExp(`${token}\\s*:`))
    }
    expect(root).toContain('#1c1b19')
    expect(root).toContain('#e0a181')
    expect(light).toContain('#f4efe6')
    expect(light).toContain('#8f4128')
    expect(root).toContain('--dur-fast: 140ms')
    expect(root).toContain('--dur: 240ms')
    expect(root).toContain('--dur-theme: 700ms')
    expect(root).toContain('--ease: cubic-bezier(0.2, 0, 0, 1)')
    expect(theme).toMatch(
      /prefers-reduced-motion:\s*reduce[\s\S]*--dur-fast:\s*1ms[\s\S]*--dur:\s*1ms[\s\S]*--dur-theme:\s*1ms/,
    )

    for (const selector of ['.btn', '.btn:hover', '.btn-ghost', '.btn-ghost:hover', '.btn-danger', '.btn-danger:hover', '.banner', '.banner.error']) {
      expectBothFaces(ruleset(theme, selector), selector)
    }
    expect(ruleset(theme, '.btn-ghost')).toContain('border-color: transparent')
    expect(ruleset(theme, '.banner.error')).toContain('background: var(--danger-wash)')
    expect(ruleset(theme, 'button,\ninput,\nselect,\ntextarea')).toMatch(/background:\s*var\(--paper\)/)
  })

  it('does not use --accent as a text color, and the focus ring uses --accent-text', () => {
    const offenders: string[] = []
    for (const file of walk(join(pageRoot, 'src'))) {
      const text = readFileSync(file, 'utf8')
      if (/(?<![\w-])color\s*:\s*var\(\s*--accent\s*\)/.test(text)) offenders.push(file)
    }
    expect(offenders).toEqual([])

    const base = readPage('src/styles/base.css')
    const chat = readPage('src/styles/chat.css')
    const shell = readPage('src/styles/shell.css')
    expect(ruleset(base, ':focus-visible')).toContain('outline: 2px solid var(--accent-text)')
    expect(ruleset(base, ':focus-visible')).not.toMatch(/border-radius/)
    expect(ruleset(chat, '.owl-chat-input:focus-visible')).toContain('outline: 2px solid var(--accent-text)')
    expect(ruleset(shell, '.owl-hero-button:focus-visible')).toContain('outline: 2px solid var(--accent-text)')
    expect(`${base}\n${chat}\n${shell}`).not.toMatch(/outline:\s*2px solid var\(--accent\)/)
  })

  it('squares the listed chrome and leaves the round owl, spine, and ring', () => {
    const chat = readPage('src/styles/chat.css')
    const shell = readPage('src/styles/shell.css')
    const art = readPage('src/styles/art.css')
    const forms = readPage('src/styles/forms.css')
    const tree = readPage('src/styles/tree.css')

    for (const selector of ['.owl-chat', '.owl-chat-code', '.owl-chat-pre', '.owl-chat-input']) {
      const block = ruleset(chat, selector)
      expect(block, selector).not.toMatch(/border-radius/)
      expect(block, selector).not.toMatch(/box-shadow/)
    }
    expect(ruleset(chat, '.owl-chat-input')).toContain('color: var(--ink)')
    expect(ruleset(chat, '.owl-chat-input')).toContain('background: var(--paper)')
    expect(ruleset(shell, '.owl-bubble')).not.toMatch(/border-radius|box-shadow/)
    expect(ruleset(art, '.art-open')).not.toMatch(/border-radius/)
    expect(ruleset(art, '.art-overlay img')).not.toMatch(/border-radius/)
    expect(ruleset(forms, '.switch')).not.toMatch(/border-radius/)
    expect(ruleset(forms, '.switch::after')).not.toMatch(/border-radius/)
    expect(chat).not.toMatch(/box-shadow/)
    expect(shell.match(/box-shadow\s*:[^;]+/g)).toEqual(['box-shadow: none'])

    expect(ruleset(shell, '.owl-hero-button')).toMatch(/border-radius:\s*50%/)
    expect(ruleset(tree, '.spine-dot')).toMatch(/border-radius:\s*50%/)
    expect(shell).toContain('.owl-ring')

    const segment = ruleset(shell, '.theme-segment')
    expect(segment).toMatch(/min-height:\s*2\.25rem/)
    expect(segment).toMatch(/border-radius:\s*0/)
    expect(segment).toContain('background: transparent')
    expect(segment).toContain('color: var(--ink)')
    expect(ruleset(shell, '.theme-segment:hover')).toContain('background: var(--chip)')
    expect(ruleset(shell, '.theme-segment:has(:checked)')).toContain('background: transparent')
    expect(ruleset(shell, '.theme-segment:has(:checked)')).toContain('color: var(--ink)')

    const thumbCss = readPage('src/components/ThemeControl.css')
    const thumb = ruleset(thumbCss, '.theme-thumb')
    expect(thumb).toMatch(/border-radius:\s*12px/)
    expect(thumb).not.toMatch(/border-radius:\s*999px|border-radius:\s*0/)
    expect(thumb).not.toMatch(/width:\s*2\.25rem/)
    expect(thumb).toMatch(/height:\s*2\.25rem/)
    expect(thumb).toMatch(/z-index:\s*1/)
    expect(thumb).toContain('pointer-events: none')
    expect(thumb).toContain('background: color-mix(in srgb, var(--paper-raised) 10%, transparent)')
    expect(thumb).toContain('transition: transform var(--dur) var(--ease), width var(--dur) var(--ease)')
    expect(thumb).not.toMatch(/backdrop-filter|box-shadow|will-change/)
    expect(ruleset(thumbCss, '.theme-thumb.is-moving')).toContain('will-change: transform, width')
    expect(thumbCss).not.toContain('.theme-thumb::after')
    expect(segment).toMatch(/z-index:\s*0/)
    const fallback = thumbCss.slice(thumbCss.indexOf('@supports not'))
    expect(fallback).toContain('background: var(--ink)')
    expect(fallback).toContain('color: var(--paper)')
    expect(fallback).toContain('z-index: 0')
    expect(fallback).toContain('z-index: 1')
    expect(thumbCss).not.toMatch(/box-shadow/)
    const control = readPage('src/components/ThemeControl.tsx')
    expect(control).toContain('import(\'@samasante/liquid-glass\')')
    expect(control.match(/<Glass/g)).toHaveLength(1)
    expect(control).toContain('const THUMB_RADIUS = 12')
    expect(control).toContain('radius={THUMB_RADIUS}')
    expect(control).not.toContain('999')
    expect(control).toContain('width: selected.offsetWidth')
    expect(control).toContain('frost: 0')
    expect(control).toContain('bend: 1')
    expect(control).toContain('bendWidth: 0.9')
    expect(control).toContain('strength: 0.18')

    const narrow = shell.slice(shell.indexOf('@media (max-width: 620px)'))
    expect(narrow).toContain('.brand-name')
    expect(narrow).toContain('display: none')
    expect(narrow).not.toContain('.theme-switch')
    expect(narrow).not.toContain('.header-right')
  })
})
