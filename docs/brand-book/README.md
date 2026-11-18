# Brand book

Rules for any web page in this system. A page-specific layout lives under that namespace's `frontend/`.

Rules Group Pages
 - A page does not store tokens and does not implement its own authorization.
 - A page decides what to show. The edge decides what to allow.
 - No UI kit. No runtime CSS. Style with CSS variables.
 - The first JavaScript payload of a page stays within 95 KB gzip. The build fails above that.
 - One entry action for sign-in. No password form, no registration form, no password reset.

Visual tokens (color, type, spacing) are not decided yet.
