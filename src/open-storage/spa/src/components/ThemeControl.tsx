import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import type { Preference } from "../theme";
import { prefersReducedMotion } from "../hooks/useReducedMotion";
import { mountGlassLens } from "./glassLens";
import { mountThemeBlob, type BlobMount } from "./themeBlob";
import { ViewportPortal } from "./ui/ViewportPortal";
import { MORPH_LEAD, OPTIONS, PopoverController, isOutsidePress, rowIndex, within, type RowEvent } from "./themePopover";
import "./ThemeControl.css";

const icons = {
  light: Sun,
  dark: Moon,
  system: Monitor,
} as const;

const optionIndex = (value: Preference): number => OPTIONS.findIndex((option) => option.value === value);

/**
 * One round glass trigger and a glass popover of three radios. The reveal, the
 * persistence and the `Header` contract (`onChange(value, origin, group)`) are
 * inherited from US-09; only the face changes here.
 */
export function ThemeControl({
  preference,
  onChange,
}: {
  preference: Preference;
  onChange: (next: Preference, origin: DOMRect, group: HTMLElement) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const blobHostRef = useRef<HTMLDivElement>(null);
  const [controller] = useState(() => new PopoverController());
  const [open, setOpen] = useState(controller.open);
  // A row to focus once the popover exists; null when the popover opened for a pointer.
  const [focusRow, setFocusRow] = useState<number | null>(null);
  // A keyup follows the keydown of the same key press; a native click follows neither.
  const keyPressed = useRef(false);
  // The blob follows the pointer and the focused row; -1 sends it away from the rows.
  const blobTarget = useRef<number>(-1);
  const blobPointer = useRef<{ x: number; y: number } | null>(null);
  const blobRef = useRef<BlobMount | null>(null);
  // The row the pointer left the blob on, restored when the pointer comes back.
  const blobRemembered = useRef<number>(-1);
  const [hovering, setHovering] = useState(false);
  // The surface widens first and the panel follows: see `MORPH_LEAD` in themePopover.ts.
  const morphIn = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Read per render, not per mount: a preference change on the OS re-reads the query.
  const instant = prefersReducedMotion();

  // The plate's lens samples the backdrop when the layout changes. It does not
  // own a frame: the blob loop is the only animation clock, and it is mounted
  // only while the popover is open.
  useLayoutEffect(() => {
    const plate = rootRef.current;
    if (!plate) return;
    const lens = mountGlassLens(plate, () => plate.dataset.glass !== "open");
    lens.paint();
    const repaint = () => lens.paint();
    window.addEventListener("scroll", repaint, { passive: true, capture: true });
    window.addEventListener("resize", repaint);
    const theme = new MutationObserver(repaint);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      lens.dispose();
      window.removeEventListener("scroll", repaint, true);
      window.removeEventListener("resize", repaint);
      theme.disconnect();
    };
  }, [open, hovering]);

  // The panel is on the body; its place is the trigger's box, read when it opens.
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    setAnchor(null);
    const place = () => {
      const box = triggerRef.current?.getBoundingClientRect();
      if (!box) return;
      setAnchor({ top: Math.round(box.bottom - 6), right: Math.round(window.innerWidth - box.right) });
    };
    place();
    window.addEventListener("scroll", place, { passive: true, capture: true });
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  // While open, listen on the document: a pointer move is reported on whatever is
  // under it, and the control must hear the moves that cross from trigger to panel.
  // No dependency list on purpose: every render re-binds the listener to the
  // render's own `aimAtPointer`. With `[open]` the first render's closure would
  // keep listening, and that closure still had a null blob host from before the
  // popover existed, so no move was ever recorded.
  useEffect(() => {
    if (!open) return;
    const onMove = (event: PointerEvent) => aimAtPointer(event);
    document.addEventListener("pointermove", onMove, { passive: true });
    return () => document.removeEventListener("pointermove", onMove);
  });

  // A pointer that reaches the trigger widens the surface, then the panel follows.
  // No `open` in the deps: opening must not re-run this effect and cancel itself.
  useEffect(() => {
    if (!hovering) return;
    morphIn.current = setTimeout(() => {
      morphIn.current = null;
      controller.pointerEnter();
    }, MORPH_LEAD);
    return () => {
      if (morphIn.current) {
        clearTimeout(morphIn.current);
        morphIn.current = null;
      }
    };
  }, [hovering, controller]);

  useEffect(() => {
    const sync = () => setOpen(controller.open);
    const unsubscribe = controller.subscribe(sync);
    sync();
    return () => {
      unsubscribe();
      controller.dispose();
    };
  }, [controller]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    // `blur` carries no target, hence the capture phase.
    const onPress = (event: PointerEvent | FocusEvent) => {
      if (isOutsidePress(event, [rootRef.current, popoverRef.current])) controller.closeNow();
    };
    // A portaled row is not inside the trigger. Focus moving between rows, or a
    // press on a row, is still inside the control.
    const onFocusOut = (event: FocusEvent) => {
      const next = event.relatedTarget;
      if (!next) return;
      if (within(next, rootRef.current) || within(next, popoverRef.current)) return;
      controller.closeNow();
    };
    // A page that sees focus without a focused window was focused by a switch,
    // not by a pointer or a `Tab`; the control must not sit open behind it.
    const release = () => {
      if (!document.hasFocus()) window.dispatchEvent(new FocusEvent("blur"));
    };
    const onFocusIn = () => release();
    const onVisibility = () => {
      if (document.visibilityState !== "visible") release();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && controller.open) {
        event.preventDefault();
        controller.closeNow();
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPress, true);
    window.addEventListener("blur", onPress, true);
    document.addEventListener("focusout", onFocusOut, true);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("pointerdown", onPress, true);
      window.removeEventListener("blur", onPress, true);
      document.removeEventListener("focusout", onFocusOut, true);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [controller]);

  // The blob exists only while the popover does. With the pointer on the
  // control it lives inside the trigger and travels with the cursor; otherwise
  // it is the well on the row of the current choice.
  useLayoutEffect(() => {
    const rows = popoverRef.current?.querySelector("[role='radiogroup']");
    // The bubble keeps the blob while the pointer is on the trigger; the list
    // takes it once the pointer is over a row, and always once it is gone.
    const overPanel = blobPointer.current !== null && blobTarget.current >= 0;
    const anchor = hovering && !overPanel ? triggerRef.current?.parentElement : blobHostRef.current;
    if (!open || !rows || !anchor) return;
    const mount = mountThemeBlob({
      host: anchor,
      rows,
      active: () => blobTarget.current,
      pointer: () => (hovering ? blobPointer.current : null),
      instant,
    });
    blobRef.current = mount;
    return () => {
      mount.dispose();
      blobRef.current = null;
    };
  }, [open, hovering, instant]);

  useLayoutEffect(() => {
    if (!open) return;
    blobRef.current?.sync();
  }, [open, anchor]);


  const aim = (index: number) => {
    if (index === blobTarget.current) return;
    blobTarget.current = index;
    blobRef.current?.sync();
  };

  /**
   * The blob's own geometry comes from the pointer: off the rows it is a circle
   * under the cursor, over one row a well leaning toward it. The blob element
   * sits inside the trigger, so it travels the way a cursor would.
   */
  const aimAtPointer = (event: { clientX: number; clientY: number }) => {
    const control = rootRef.current;
    const anchor = triggerRef.current;
    if (!control || !anchor) return;
    const box = anchor.getBoundingClientRect();
    blobPointer.current = { x: event.clientX - box.left, y: event.clientY - box.top };
    const panel = popoverRef.current?.getBoundingClientRect();
    const overPanel =
      !!panel &&
      event.clientX >= panel.left &&
      event.clientX <= panel.right &&
      event.clientY >= panel.top &&
      event.clientY <= panel.bottom;
    if (!overPanel) {
      aim(-1);
      return;
    }
    for (const [index, row] of rowRefs.current.entries()) {
      if (!row) continue;
      const rect = row.getBoundingClientRect();
      if (event.clientY >= rect.top && event.clientY <= rect.bottom) {
        aim(index);
        return;
      }
    }
    aim(-1);
  };

  useLayoutEffect(() => {
    if (!open || focusRow === null) return;
    const row = popoverRef.current?.querySelectorAll<HTMLButtonElement>(".theme-row")[focusRow];
    setFocusRow(null);
    if (!row) return;
    // A row moves the ring with its own arrow keys, and a nested button cannot
    // hold focus inside the header's round glass button, so the row also shows
    // its ring while the trigger keeps focus.
    row.dataset.focusRing = "current";
    row.focus();
    row.scrollIntoView?.({ block: "nearest" });
  }, [open, focusRow]);

  /** Open from the keyboard or a reader and land on the current choice. */
  const openAt = (index: number) => {
    blobTarget.current = index;
    blobPointer.current = null;
    controller.requestOpen();
    setOpen(controller.open);
    setFocusRow(index);
  };

  const choose = (next: Preference) => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    // The circle starts at the trigger, so measure it before the panel unmounts.
    const origin = trigger.getBoundingClientRect();
    trigger.focus();
    onChange(next, origin, trigger);
    controller.closeNow();
    setOpen(controller.open);
  };

  const move = (index: number, move: RowEvent) => {
    const target = rowIndex(index, move);
    if (target < 0) return;
    // The keyboard has no pointer: the blob glides to the focused row instead.
    blobPointer.current = null;
    aim(target);
    for (const [at, row] of rowRefs.current.entries()) {
      if (row) row.dataset.focusRing = at === target ? "current" : "";
    }
    rowRefs.current[target]?.focus();
  };

  const rowKeys = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    const index = rowRefs.current.findIndex((row) => row === event.currentTarget);
    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight":
        event.preventDefault();
        move(index, { type: "next" });
        return;
      case "ArrowUp":
      case "ArrowLeft":
        event.preventDefault();
        move(index, { type: "previous" });
        return;
      case "Home":
        event.preventDefault();
        move(index, { type: "home" });
        return;
      case "End":
        event.preventDefault();
        move(index, { type: "end" });
        return;
      case "Escape":
        event.preventDefault();
        controller.closeNow();
        setOpen(controller.open);
        triggerRef.current?.focus();
        return;
      case "Enter":
      case " ":
      case "Spacebar":
        // Enter and Space both press on keydown. Choosing on keyup, and letting
        // the click native to that key press pass, keeps one choice per press.
        event.preventDefault();
        keyPressed.current = true;
        return;
      default:
        return;
    }
  };

  const SelectedIcon = icons[preference];

  return (
    <div
      ref={rootRef}
      className="theme-control header-glass-bubble glass-material"
      data-glass={open ? "open" : "closed"}
      data-glass-hover={hovering ? "true" : "false"}
      onPointerEnter={() => {
        blobRemembered.current = blobTarget.current;
        blobTarget.current = optionIndex(preference);
        blobPointer.current = null;
        setHovering(true);
      }}
      onPointerMove={aimAtPointer}
      onPointerLeave={(event) => {
        if (morphIn.current) {
          clearTimeout(morphIn.current);
          morphIn.current = null;
        }
        const next = event.relatedTarget;
        if (within(next, rootRef.current) || within(next, popoverRef.current)) {
          controller.pointerStay();
          return;
        }
        setHovering(false);
        // Unconditional: the controller decides whether a grace close is due. Asking
        // `controller.open` here reads the pre-render value on the frame that opened it.
        controller.pointerLeave();
        // No pointer over the rows: the blob rests on the current choice.
        blobTarget.current = optionIndex(preference);
        blobPointer.current = null;
        blobRef.current?.sync();
      }}
      onFocusCapture={(event) => {
        // A click focuses the trigger before the panel exists: no pointer to arm, nothing to hold.
        if (within(event.target, triggerRef.current) && controller.open) controller.pointerStay();
      }}
    >
      <span className="theme-trigger-wrap">
        <button
          ref={triggerRef}
          type="button"
          className="theme-trigger"
          aria-label={`Theme: ${preference}`}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls="theme-popover"
          data-preference={preference}
                    onClick={() => openAt(optionIndex(preference))}
          onKeyDown={(event) => {
            if ((event.key === "Enter" || event.key === " " || event.key === "ArrowDown") && !open) {
              event.preventDefault();
              openAt(optionIndex(preference));
            }
          }}
        >
          <SelectedIcon aria-hidden="true" className="theme-trigger-icon" />
        </button>
        <span className="theme-tooltip" aria-hidden="true">
          Theme
        </span>
      </span>

      {/* On the body: the header paints over its own overflow, so a panel that
          descends from it is not hit-testable and would close on the way in. */}
      {open ? (
        <ViewportPortal>
        <div
          id="theme-popover"
          ref={popoverRef}
          className={instant ? "theme-popover is-instant" : open ? "theme-popover is-opening" : "theme-popover"}
          role="dialog"
          aria-label="Theme"
          style={anchor ? { top: anchor.top, right: anchor.right } : undefined}
        >
          <div className="theme-popover-panel theme-popover-glass glass-material">
            <div className="theme-rows" role="radiogroup" aria-label="Theme">
              {/* geometry, the spring and the paint element live in themeBlob.ts */}
              <div
                ref={blobHostRef}
                className="theme-popover-glass"
                style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
              />
              {OPTIONS.map((option, index) => {
                const Icon = icons[option.value];
                const active = option.value === preference;
                const fallback = index === 0 && optionIndex(preference) < 0;
                return (
                  <button
                    key={option.value}
                    ref={(node) => {
                      rowRefs.current[index] = node;
                    }}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    tabIndex={active || fallback ? 0 : -1}
                    className={active ? "theme-row is-active" : "theme-row"}
                    data-value={option.value}
                    onKeyDown={rowKeys}
                    onKeyUp={(event) => {
                      if (!keyPressed.current) return;
                      if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") return;
                      event.preventDefault();
                      choose(option.value);
                    }}
                    onClick={() => {
                      if (keyPressed.current) {
                        keyPressed.current = false;
                        return;
                      }
                      choose(option.value);
                    }}
                  >
                    <Icon aria-hidden="true" className="theme-row-icon" />
                    <span className="theme-row-label">{option.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        </ViewportPortal>
      ) : null}
    </div>
  );
}
