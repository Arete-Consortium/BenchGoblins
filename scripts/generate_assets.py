#!/usr/bin/env python3
"""Generate app icon and splash screen assets for GameSpace."""

from PIL import Image, ImageDraw, ImageFont
import math
import os

# Brand colors
BACKGROUND = "#0f0f1a"
PRIMARY = "#4f46e5"  # Indigo
ACCENT = "#818cf8"   # Light indigo
GOLD = "#fbbf24"     # For pro/premium feel


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def create_app_icon(size: int = 1024, output_path: str = "icon.png"):
    """Create the GameSpace app icon."""
    img = Image.new("RGB", (size, size), hex_to_rgb(BACKGROUND))
    draw = ImageDraw.Draw(img)

    center = size // 2

    # Draw outer ring (represents the "space" / arena)
    ring_radius = int(size * 0.38)
    ring_width = int(size * 0.04)
    draw.ellipse(
        [center - ring_radius, center - ring_radius,
         center + ring_radius, center + ring_radius],
        outline=hex_to_rgb(PRIMARY),
        width=ring_width
    )

    # Draw stylized "G" using geometric shapes
    # Main arc of G
    g_radius = int(size * 0.28)
    g_width = int(size * 0.08)

    # Draw the G as an arc (270 degrees, open on the right)
    bbox = [center - g_radius, center - g_radius,
            center + g_radius, center + g_radius]
    draw.arc(bbox, start=45, end=315, fill=hex_to_rgb(ACCENT), width=g_width)

    # Draw the horizontal bar of G
    bar_length = int(size * 0.18)
    bar_height = int(size * 0.07)
    bar_x = center - int(size * 0.02)
    bar_y = center - bar_height // 2
    draw.rectangle(
        [bar_x, bar_y, bar_x + bar_length, bar_y + bar_height],
        fill=hex_to_rgb(ACCENT)
    )

    # Add three small dots representing decision points / stats
    dot_radius = int(size * 0.025)
    dot_positions = [
        (center - int(size * 0.15), center - int(size * 0.18)),  # top left
        (center + int(size * 0.12), center - int(size * 0.12)),  # top right
        (center - int(size * 0.08), center + int(size * 0.20)),  # bottom
    ]

    for i, (dx, dy) in enumerate(dot_positions):
        color = hex_to_rgb(GOLD) if i == 0 else hex_to_rgb(PRIMARY)
        draw.ellipse(
            [dx - dot_radius, dy - dot_radius,
             dx + dot_radius, dy + dot_radius],
            fill=color
        )

    img.save(output_path, "PNG")
    print(f"Created: {output_path} ({size}x{size})")
    return img


def create_adaptive_icon(size: int = 1024, output_path: str = "adaptive-icon.png"):
    """Create adaptive icon for Android (with more padding)."""
    # Adaptive icons need ~30% safe zone, so we create icon at 70% size centered
    img = Image.new("RGB", (size, size), hex_to_rgb(BACKGROUND))

    # Create the icon content at smaller size
    icon_size = int(size * 0.65)
    icon = create_icon_content(icon_size)

    # Paste centered
    offset = (size - icon_size) // 2
    img.paste(icon, (offset, offset))

    img.save(output_path, "PNG")
    print(f"Created: {output_path} ({size}x{size})")
    return img


def create_icon_content(size: int) -> Image.Image:
    """Create just the icon content without background padding."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = size // 2

    # Draw outer ring
    ring_radius = int(size * 0.42)
    ring_width = int(size * 0.05)
    draw.ellipse(
        [center - ring_radius, center - ring_radius,
         center + ring_radius, center + ring_radius],
        outline=hex_to_rgb(PRIMARY),
        width=ring_width
    )

    # Draw stylized "G"
    g_radius = int(size * 0.30)
    g_width = int(size * 0.09)

    bbox = [center - g_radius, center - g_radius,
            center + g_radius, center + g_radius]
    draw.arc(bbox, start=45, end=315, fill=hex_to_rgb(ACCENT), width=g_width)

    # Horizontal bar
    bar_length = int(size * 0.20)
    bar_height = int(size * 0.08)
    bar_x = center - int(size * 0.02)
    bar_y = center - bar_height // 2
    draw.rectangle(
        [bar_x, bar_y, bar_x + bar_length, bar_y + bar_height],
        fill=hex_to_rgb(ACCENT)
    )

    # Decision dots
    dot_radius = int(size * 0.03)
    dot_positions = [
        (center - int(size * 0.16), center - int(size * 0.20)),
        (center + int(size * 0.14), center - int(size * 0.14)),
        (center - int(size * 0.10), center + int(size * 0.22)),
    ]

    for i, (dx, dy) in enumerate(dot_positions):
        color = hex_to_rgb(GOLD) if i == 0 else hex_to_rgb(PRIMARY)
        draw.ellipse(
            [dx - dot_radius, dy - dot_radius,
             dx + dot_radius, dy + dot_radius],
            fill=color
        )

    return img


def create_splash_icon(size: int = 200, output_path: str = "splash-icon.png"):
    """Create splash screen icon (smaller, for center of splash)."""
    # Create on transparent background
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = size // 2

    # Simplified G logo
    g_radius = int(size * 0.35)
    g_width = int(size * 0.12)

    bbox = [center - g_radius, center - g_radius,
            center + g_radius, center + g_radius]
    draw.arc(bbox, start=45, end=315, fill=hex_to_rgb(ACCENT), width=g_width)

    # Horizontal bar
    bar_length = int(size * 0.22)
    bar_height = int(size * 0.10)
    bar_x = center - int(size * 0.02)
    bar_y = center - bar_height // 2
    draw.rectangle(
        [bar_x, bar_y, bar_x + bar_length, bar_y + bar_height],
        fill=hex_to_rgb(ACCENT)
    )

    img.save(output_path, "PNG")
    print(f"Created: {output_path} ({size}x{size})")
    return img


def create_favicon(size: int = 48, output_path: str = "favicon.png"):
    """Create favicon for web."""
    img = Image.new("RGB", (size, size), hex_to_rgb(BACKGROUND))
    draw = ImageDraw.Draw(img)

    center = size // 2

    # Simple G at small size
    g_radius = int(size * 0.32)
    g_width = max(3, int(size * 0.12))

    bbox = [center - g_radius, center - g_radius,
            center + g_radius, center + g_radius]
    draw.arc(bbox, start=45, end=315, fill=hex_to_rgb(ACCENT), width=g_width)

    # Bar
    bar_length = int(size * 0.20)
    bar_height = max(3, int(size * 0.10))
    bar_x = center - int(size * 0.02)
    bar_y = center - bar_height // 2
    draw.rectangle(
        [bar_x, bar_y, bar_x + bar_length, bar_y + bar_height],
        fill=hex_to_rgb(ACCENT)
    )

    img.save(output_path, "PNG")
    print(f"Created: {output_path} ({size}x{size})")
    return img


def main():
    # Output directory
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "src", "mobile", "assets"
    )
    os.makedirs(output_dir, exist_ok=True)

    # Generate all assets
    create_app_icon(1024, os.path.join(output_dir, "icon.png"))
    create_adaptive_icon(1024, os.path.join(output_dir, "adaptive-icon.png"))
    create_splash_icon(200, os.path.join(output_dir, "splash-icon.png"))
    create_favicon(48, os.path.join(output_dir, "favicon.png"))

    print("\nAll assets generated successfully!")
    print(f"Location: {output_dir}")


if __name__ == "__main__":
    main()
