'use client';

interface GoblinIconProps {
  className?: string;
}

export function GoblinIcon({ className = 'h-6 w-6' }: GoblinIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {/* Pointed ears */}
      <path d="M4 8L2 3L6 6" />
      <path d="M20 8L22 3L18 6" />

      {/* Head shape */}
      <ellipse cx="12" cy="13" rx="8" ry="9" />

      {/* Menacing eyes */}
      <path d="M7 11L10 12L7 13" fill="currentColor" />
      <path d="M17 11L14 12L17 13" fill="currentColor" />

      {/* Mischievous grin */}
      <path d="M8 17C8 17 10 19 12 19C14 19 16 17 16 17" />
      <path d="M9 17L9.5 18" />
      <path d="M15 17L14.5 18" />

      {/* Nose */}
      <path d="M12 13L11 15H13L12 13" fill="currentColor" />
    </svg>
  );
}

export default GoblinIcon;
