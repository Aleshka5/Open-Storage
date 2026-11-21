import { Art } from '../../../../components/art/Art'

export default function ArtNode() {
  return (
    <>
      <p className="lede">
        The owl is the site's mascot. It changes mood with whoever is reading — angry for a
        guest, calm once you are signed in, kind for an admin — and the same drawings come back
        as the tab icon and the corner button.
      </p>
      <Art />
    </>
  )
}
