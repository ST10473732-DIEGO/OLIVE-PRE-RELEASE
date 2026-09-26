import { useId } from "react";

/** The OLIVE mark: a green olive with its pimento. The same drawing is the
 *  app icon (assets/branding/olive-mark.svg); keep the two in step. */
export function OliveLogo({ className = "", size }: { className?: string; size?: number }) {
  const id = useId();
  return (
    <svg
      className={`olive-logo ${className}`.trim()}
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      data-logo={id}
    >
      <g className="olive-body">
        <ellipse cx="30" cy="35" rx="19" ry="23" transform="rotate(-28 30 35)" fill="#6F7E2E" />
        <ellipse cx="24" cy="40" rx="8" ry="12" transform="rotate(-28 24 40)" fill="#879641" opacity=".8" />
      </g>
      <ellipse className="olive-shine" cx="22" cy="30" rx="3" ry="6" transform="rotate(-28 22 30)" fill="#fff" opacity=".35" />
      <g className="olive-pim">
        <ellipse cx="42.5" cy="16.5" rx="8" ry="6.2" transform="rotate(-28 42.5 16.5)" fill="#D9492F" />
        <ellipse cx="42" cy="16" rx="4" ry="2.6" transform="rotate(-28 42 16)" fill="#F07A5C" opacity=".7" />
      </g>
    </svg>
  );
}
