import { useCallback, useId, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/**
 * A hover/focus tooltip anchored to its trigger.
 *
 * It renders into a portal on document.body with `position: fixed` rather than as an
 * absolutely-positioned child. Both tables live inside an `overflow-x: auto` wrapper,
 * and an overflow container clips descendants on *both* axes -- a nested tooltip would
 * be cut off at the row edge. A portal escapes that entirely, and fixed coordinates let
 * the tip flip below the trigger when there is no room above it.
 */

const GAP = 8
const MARGIN = 8
const MAX_WIDTH = 300

interface Position {
  top: number
  left: number
  below: boolean
}

interface Props {
  /** The tooltip body. */
  content: ReactNode
  /** Extra classes for the trigger element. */
  className?: string
  children: ReactNode
}

export function Tooltip({ content, className, children }: Props) {
  const id = useId()
  const anchor = useRef<HTMLSpanElement>(null)
  const [position, setPosition] = useState<Position | null>(null)

  const show = useCallback(() => {
    const rect = anchor.current?.getBoundingClientRect()
    if (!rect) return

    // Above by default; below when the trigger is too near the top of the viewport
    // (column headers, mostly) for the tip to fit.
    const below = rect.top < 200
    setPosition({
      top: below ? rect.bottom + GAP : rect.top - GAP,
      left: Math.min(rect.left, window.innerWidth - MAX_WIDTH - MARGIN),
      below,
    })
  }, [])

  const hide = useCallback(() => setPosition(null), [])

  return (
    <>
      <span
        ref={anchor}
        className={className}
        // tabIndex makes the tooltip reachable by keyboard, not just by mouse.
        tabIndex={0}
        aria-describedby={position ? id : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        {children}
      </span>

      {position &&
        createPortal(
          <span
            role="tooltip"
            id={id}
            className={`tooltip${position.below ? ' tooltip--below' : ''}`}
            style={{ top: position.top, left: Math.max(MARGIN, position.left) }}
          >
            {content}
          </span>,
          document.body,
        )}
    </>
  )
}
