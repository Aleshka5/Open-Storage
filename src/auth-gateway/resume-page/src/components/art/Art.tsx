import { useState } from 'react'
import calm from '../../assets/My_icon_calm.svg'
import angry from '../../assets/My_icon_angry.svg'
import kind from '../../assets/My_icon_kind.svg'
import tab from '../../assets/My_icon_for_tab.svg'
import heroShot from '../../assets/hero.png'

/**
 * The owl's art, side by side. The owl itself shows one mood at a time and the
 * page never asks which; this page is where the drawings are actually seen, so
 * a change to an icon or to a clip can be checked without signing in and out.
 *
 * The clips are served from `public/owl-clips/` rather than imported: they are
 * SMIL animations that run on load, and an `<img>` to the file is enough.
 */

const stills = [
  { name: 'Calm', src: calm, note: 'The resting frame: a guest, and reduced motion.' },
  { name: 'Angry', src: angry, note: 'Hold frame of calm-to-angry.' },
  { name: 'Kind', src: kind, note: 'Hold frame of calm-to-kind: realm admin.' },
  { name: 'Tab icon', src: tab, note: 'The favicon. Same drawing, square canvas.' },
] as const

const clips = [
  { name: 'calm-to-angry', src: '/owl-clips/calm-to-angry.svg', note: 'Guest.' },
  { name: 'angry-to-calm', src: '/owl-clips/angry-to-calm.svg', note: 'Signed in.' },
  { name: 'calm-to-kind', src: '/owl-clips/calm-to-kind.svg', note: 'Realm admin.' },
] as const

export function Art() {
  const [big, setBig] = useState<string | null>(null)

  return (
    <div className="art">
      <section className="art-section">
        <h2 className="art-heading">Still frames</h2>
        <div className="art-grid">
          {stills.map((s) => (
            <figure key={s.name} className="art-cell">
              <button className="art-open" type="button" onClick={() => setBig(s.src)}>
                <img className="art-still" src={s.src} alt={s.name} loading="lazy" width={128} height={128} />
              </button>
              <figcaption>
                <span className="art-name">{s.name}</span>
                <span className="art-note">{s.note}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="art-section">
        <h2 className="art-heading">Clips</h2>
        <div className="art-grid">
          {clips.map((c) => (
            <figure key={c.name} className="art-cell">
              <button className="art-open" type="button" onClick={() => setBig(c.src)}>
                <img className="art-clip" src={c.src} alt={`${c.name} clip`} width={128} height={128} />
              </button>
              <figcaption>
                <span className="art-name">{c.name}</span>
                <span className="art-note">{c.note}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="art-section">
        <h2 className="art-heading">Elsewhere</h2>
        <div className="art-grid">
          <figure className="art-cell">
            <button className="art-open" type="button" onClick={() => setBig(heroShot)}>
              <img className="art-still" src={heroShot} alt="Landing illustration" loading="lazy" width={128} height={128} />
            </button>
            <figcaption>
              <span className="art-name">hero.png</span>
              <span className="art-note">Travels with the owl art. No node uses it yet.</span>
            </figcaption>
          </figure>
        </div>
      </section>

      {big ? (
        <div
          className="art-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Full-size art"
          onClick={() => setBig(null)}
        >
          <img src={big} alt="" />
          <button className="btn btn-small" type="button" onClick={() => setBig(null)}>
            Close
          </button>
        </div>
      ) : null}
    </div>
  )
}
