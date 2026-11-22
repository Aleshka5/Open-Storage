import { lazy, Suspense, useCallback, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation } from 'react-router-dom'
import calmToAngry from '../../assets/animations/calm-to-angry.svg?raw'
import angryToCalm from '../../assets/animations/angry-to-calm.svg?raw'
import calmToKind from '../../assets/animations/calm-to-kind.svg?raw'
import restingCalm from '../../assets/My_icon_calm.svg?raw'
import { useAuth } from '../../auth'
import { prefersReducedMotion } from '../../hooks/useReducedMotion'
import { isAdmin, type User } from '../../types'
import { OwlBubble } from './OwlBubble'

/** The panel and its streaming client stay out of the initial bundle. */
const OwlChat = lazy(() => import('./OwlChat'))

/**
 * The owl. One component, two states, driven by `document.documentElement.dataset.owl`
 * which `useScrollChrome` writes:
 *
 *   hero   — parked in the 128px slot at the top of the node, not a control
 *   docked — a real "Back to top" button in the bottom-right corner
 *
 * The hero owl is also the way into the chat: clicking it opens the panel.
 * Docked, it goes back to being the "Back to top" button — a corner button that
 * changed meaning on scroll would be worse than two separate affordances.
 *
 * This is a two-element cross-fade, not FLIP. FLIP needs the hero transform
 * re-measured on every scroll frame, which fights the 240ms transition that
 * makes the dock/undock morph — the owl ends up trailing the page. Two elements
 * cost one extra SVG injection and behave correctly: the hero owl sits in the
 * flow and scrolls with the page, the docked button is fixed, and they cross-fade
 * on the same `data-owl` attribute.
 *
 * The mood is picked from the session, so there are three clips: `calm-to-angry`
 * for a guest, `angry-to-calm` signed in, `calm-to-kind` for a realm admin.
 * Under reduced motion every clip collapses to the resting frame.
 */

type OwlClip = 'guest' | 'user' | 'admin'

function stripXml(raw: string): string {
  return raw.replace(/^\s*<\?xml[^?]*\?>\s*/i, '')
}

const clips: Record<OwlClip, { motion: string; motionName: string }> = {
  guest: { motion: stripXml(calmToAngry), motionName: 'calm-to-angry' },
  user: { motion: stripXml(angryToCalm), motionName: 'angry-to-calm' },
  admin: { motion: stripXml(calmToKind), motionName: 'calm-to-kind' },
}

const resting = stripXml(restingCalm)

function pickOwlClip(pathname: string, user: User | null): OwlClip {
  if (pathname === '/auth' || !user) return 'guest'
  if (isAdmin(user)) return 'admin'
  return 'user'
}

/** The bubble greets on arrival at the start node, and nowhere else. */
function greets(pathname: string): boolean {
  return pathname === '/'
}

export function Owl() {
  const { pathname } = useLocation()
  const { user, loading } = useAuth()
  // Arriving on the hub is the greeting: the owl introduces itself, every time.
  // Read once at mount, so walking into the tree and back does not replay it —
  // a reload does. The chat itself never opens on its own; it is the reader's
  // click on the owl, and nothing else.
  const [chatOpen, setChatOpen] = useState(false)
  const [greeting, setGreeting] = useState(() => greets(pathname))
  const clip = pickOwlClip(pathname, user)
  const spec = clips[clip]
  // The clip replays on a navigation because the host is re-injected, and under
  // reduced motion the resting frame is re-injected instead of the animation.
  const playId = `${clip}-${pathname}`
  const hostRef = useRef<HTMLDivElement>(null)
  const heroRef = useRef<HTMLDivElement>(null)
  const injectedFor = useRef<string | null>(null)

  useLayoutEffect(() => {
    if (loading) return
    const host = hostRef.current
    if (!host) return
    if (injectedFor.current === playId) return
    injectedFor.current = playId
    const markup = prefersReducedMotion() ? resting : spec.motion
    host.innerHTML = markup
    if (heroRef.current) heroRef.current.innerHTML = markup
  }, [loading, playId, spec.motion])

  // A new node drops a greeting the reader never took up; the start node raises
  // it again. The panel stays open across a navigation — it is chrome.
  const lastPath = useRef(pathname)
  if (lastPath.current !== pathname) {
    lastPath.current = pathname
    if (greets(pathname)) setGreeting(true)
  }

  const openChat = useCallback(() => {
    // The greeting asked for the click; once it comes, it has served its turn.
    setGreeting(false)
    setChatOpen(true)
  }, [])

  const closeChat = useCallback(() => setChatOpen(false), [])

  const onClick = () => {
    // The corner owl is only ever "back to top"; the hero owl opens the chat.
    // CSS makes the docked button unclickable while it is the hero; this guard
    // makes it inert for keyboard and tests.
    if (document.documentElement.dataset.owl !== 'docked') return
    const reduced = prefersReducedMotion()
    window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })
    // Keyboard users land where the eye lands.
    document.getElementById('node-article')?.querySelector('h1')?.focus()
  }

  return (
    <>
      <div className="owl-slot">
        <button
          className="owl-hero-button"
          type="button"
          aria-label="Chat with the AI owl"
          aria-expanded={chatOpen}
          onClick={openChat}
        >
          <div
            ref={heroRef}
            className="owl-hero"
            aria-hidden="true"
            data-mascot={loading ? undefined : clip}
            data-mascot-phase="motion"
            data-mascot-motion={spec.motionName}
          />
        </button>
        {greeting && greets(pathname) ? <OwlBubble onDismiss={() => setGreeting(false)} /> : null}
      </div>
      {chatOpen
        ? createPortal(
            <Suspense fallback={<div className="owl-chat owl-chat-loading">Waking the owl…</div>}>
              <OwlChat onClose={closeChat} user={user} />
            </Suspense>,
            document.body,
          )
        : null}
      <button className="owl" type="button" aria-label="Back to top" onClick={onClick}>
        <div ref={hostRef} className="owl-art" aria-hidden="true" />
        <svg className="owl-ring" viewBox="0 0 56 56" aria-hidden="true">
          <circle cx="28" cy="28" r="24" />
        </svg>
      </button>
    </>
  )
}
