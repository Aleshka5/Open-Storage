# task-02 Square chrome

Story: [US-03](../init.md)

## Outcome

Panels, fields, and focus rings on the resume page are square and have no drop shadow. Viewport layers sit on `document.body`.

## Paths

- `src/auth-gateway/resume-page/src/styles/shell.css`
- `src/auth-gateway/resume-page/src/styles/chat.css`
- `src/auth-gateway/resume-page/src/styles/art.css`
- `src/auth-gateway/resume-page/src/styles/forms.css`
- `src/auth-gateway/resume-page/src/styles/base.css`
- `src/auth-gateway/resume-page/src/components/art/Art.tsx`
- `src/auth-gateway/resume-page/src/components/owl/OwlChat.tsx`

## Done when

- The chat panel, greeting bubble, art frames, code blocks, account switch, and focus rings have square corners. The two drop shadows are gone.
- `.btn-ghost` border matches its fill. The chat field sets both faces. A 2px focus ring uses `--accent-text`.
- The owl hit target, the spine dots, and the owl progress ring stay round.
- The art lightbox and the owl chat are mounted on `document.body`.
