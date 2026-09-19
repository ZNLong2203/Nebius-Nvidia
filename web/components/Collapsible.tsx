"use client";

import { useState } from "react";

/**
 * A section that can be folded away. Long test output and long lists of failing
 * tests are worth having, but not worth pushing the patch off the screen.
 */
export function Collapsible({
  title,
  count,
  defaultOpen = true,
  children,
}: {
  title: string;
  count?: number | string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="mb-5 last:mb-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="group mb-2 flex w-full items-center gap-2 text-left"
      >
        <span
          aria-hidden
          className="text-[9px] text-ink-3 transition-transform duration-150"
          style={{ transform: open ? "rotate(90deg)" : "none" }}
        >
          ▶
        </span>
        <span className="eyebrow group-hover:text-ink-2">{title}</span>
        {count !== undefined && (
          <span className="mono tnum text-[10.5px] text-ink-3">{count}</span>
        )}
      </button>
      {open && children}
    </section>
  );
}
