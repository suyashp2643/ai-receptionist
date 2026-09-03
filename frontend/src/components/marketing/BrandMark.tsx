/**
 * Original geometric SVG mark — three overlapping rounded shapes suggesting
 * a conversation bubble and a signal/handoff, built from plain shapes only
 * (no imported artwork, no icon font, no paid or copyrighted asset).
 */
export function BrandMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <defs>
        <linearGradient id="brandmark-gradient" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#8b5cf6" />
          <stop offset="1" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <rect x="2" y="4" width="22" height="18" rx="6" fill="url(#brandmark-gradient)" />
      <circle cx="25" cy="24" r="6" fill="#0b0e1a" stroke="url(#brandmark-gradient)" strokeWidth="2" />
      <circle cx="10" cy="13" r="1.6" fill="#0b0e1a" />
      <circle cx="16" cy="13" r="1.6" fill="#0b0e1a" />
    </svg>
  );
}
