import { useEffect, useState } from 'react';

// The rendered height of an element, kept current as it grows or
// shrinks. Takes the element itself (from a callback ref), so the
// measuring starts the moment it mounts. In a test DOM nothing is laid
// out and there is no ResizeObserver, so the height stays 0.
export function useElementHeight(element: HTMLElement | null): number {
  const [height, setHeight] = useState(0);
  useEffect(() => {
    if (!element || typeof ResizeObserver === 'undefined') {
      return undefined;
    }
    const observer = new ResizeObserver(() => setHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return height;
}
