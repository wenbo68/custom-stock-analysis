import { useEffect, useState } from 'react';

// The width a scroll box's vertical scrollbar takes out of its inside,
// kept current as the box's content grows past it or shrinks back. On a
// classic scrollbar (Linux and Windows browsers) this is 15px or so
// while the box scrolls and 0 while it does not; an overlay scrollbar
// (macOS, phones) takes nothing, so it reads 0 always. Takes the box
// itself (from a callback ref), so measuring starts the moment it
// mounts; the box's inside narrows when the bar appears, which the
// observer sees. In a test DOM nothing is laid out and there is no
// ResizeObserver, so the width stays 0.
export function useScrollbarWidth(element: HTMLElement | null): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!element || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const observer = new ResizeObserver(() => setWidth(Math.max(0, element.offsetWidth - element.clientWidth)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return width;
}
