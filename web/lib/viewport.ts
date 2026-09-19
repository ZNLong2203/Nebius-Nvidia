import type { RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

export interface View {
  x: number;
  y: number;
  k: number;
}

export const MIN_K = 0.2;
export const MAX_K = 2.5;
const FIT_PADDING = 48;

export const clampScale = (k: number) => Math.min(MAX_K, Math.max(MIN_K, k));

/**
 * Pan and zoom over a fixed-size canvas.
 *
 * A scroll container was fine while trees were four nodes wide. Once a search
 * goes deep the whole shape stops fitting, and the shape is the point -- so the
 * viewport has to be steerable: drag to pan, pinch or ctrl-scroll to zoom,
 * and one key to put it all back on screen.
 *
 * It auto-fits until the first deliberate interaction, so a run that grows
 * stays entirely visible without anyone touching it, and stops the moment
 * someone takes control.
 */
export function useViewport(
  containerRef: RefObject<HTMLDivElement | null>,
  content: { width: number; height: number },
) {
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const [dragging, setDragging] = useState(false);
  const steered = useRef(false);
  const dragged = useRef(false);

  const fit = useCallback(
    (takeControl = false) => {
      const element = containerRef.current;
      if (!element || content.width === 0 || content.height === 0) return;
      const { clientWidth: w, clientHeight: h } = element;
      const k = clampScale(
        Math.min(1, (w - FIT_PADDING) / content.width, (h - FIT_PADDING) / content.height),
      );
      setView({
        k,
        x: (w - content.width * k) / 2,
        y: (h - content.height * k) / 2,
      });
      if (takeControl) steered.current = false;
    },
    [containerRef, content.width, content.height],
  );

  /* Keep the whole tree in frame while it grows, until someone steers. */
  useEffect(() => {
    if (!steered.current) fit();
  }, [fit]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      if (!steered.current) fit();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [containerRef, fit]);

  const zoomBy = useCallback(
    (factor: number, anchor?: { x: number; y: number }) => {
      const element = containerRef.current;
      if (!element) return;
      steered.current = true;
      setView((current) => {
        const k = clampScale(current.k * factor);
        if (k === current.k) return current;
        const point = anchor ?? { x: element.clientWidth / 2, y: element.clientHeight / 2 };
        // Keep whatever is under the anchor exactly where it is.
        const ratio = k / current.k;
        return {
          k,
          x: point.x - (point.x - current.x) * ratio,
          y: point.y - (point.y - current.y) * ratio,
        };
      });
    },
    [containerRef],
  );

  const panBy = useCallback((dx: number, dy: number) => {
    steered.current = true;
    setView((current) => ({ ...current, x: current.x + dx, y: current.y + dy }));
  }, []);

  /* Wheel: scroll pans, ctrl/meta-scroll zooms. Trackpad pinch arrives as the
     latter, so pinching works without any extra handling. */
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        const rect = element.getBoundingClientRect();
        zoomBy(Math.exp(-event.deltaY * 0.01), {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        });
      } else {
        panBy(-event.deltaX, -event.deltaY);
      }
    };

    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [containerRef, zoomBy, panBy]);

  const onPointerDown = useCallback(
    (event: React.PointerEvent) => {
      if (event.button !== 0) return;
      const element = containerRef.current;
      if (!element) return;

      dragged.current = false;
      let lastX = event.clientX;
      let lastY = event.clientY;
      let travelled = 0;

      const move = (moveEvent: PointerEvent) => {
        const dx = moveEvent.clientX - lastX;
        const dy = moveEvent.clientY - lastY;
        lastX = moveEvent.clientX;
        lastY = moveEvent.clientY;
        travelled += Math.abs(dx) + Math.abs(dy);
        // A few pixels of travel is a click with a shaky hand, not a drag.
        if (travelled > 4) {
          dragged.current = true;
          setDragging(true);
          panBy(dx, dy);
        }
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        setDragging(false);
      };

      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [containerRef, panBy],
  );

  /** True when the gesture that just ended was a drag, so a click is suppressed. */
  const consumedDrag = useCallback(() => dragged.current, []);

  return { view, dragging, fit, zoomBy, panBy, onPointerDown, consumedDrag };
}
