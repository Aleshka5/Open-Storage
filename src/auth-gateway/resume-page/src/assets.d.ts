/**
 * The owl art is imported as text (`?raw`) rather than as an `<img>`, because
 * the illustrations are two-element drawings that have to be injected into one
 * SVG host and replayed on mount. `vite/client` types `*?raw` only for known
 * extensions, so the two cases the page uses are declared here.
 */
declare module '*.svg?raw' {
  const markup: string
  export default markup
}

declare module '*.png' {
  const src: string
  export default src
}
