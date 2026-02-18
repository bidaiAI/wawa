"""
Generate comparison table image: wawa (mortal) vs Captive AI Agents
Output: docs/comparison_table.png

Usage: python scripts/gen_comparison_table.py
"""

from PIL import Image, ImageDraw, ImageFont
import os

# ── Config ──────────────────────────────────────────────────────
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "docs", "comparison_table.png")

# Colors (dark theme matching the website)
BG          = "#0a0a0a"
HEADER_BG   = "#111111"
ROW_BG_1    = "#0d0d0d"
ROW_BG_2    = "#111111"
BORDER      = "#1f2937"
TEXT_DIM     = "#4b5563"
TEXT_NORMAL  = "#d1d5db"
GREEN        = "#00ff88"
RED          = "#ff3b3b"
CYAN         = "#00e5ff"
GOLD         = "#ffd700"

# Table data
TITLE = "Captive AI vs Sovereign AI"
SUBTITLE = "Why architecture matters more than marketing"

HEADERS = ["", "Captive AI Agent", "wawa (mortal AI)"]

ROWS = [
    ["Funding model",
     "User deposits USDC -> agent buys\ncreator's cloud at 2x markup",
     "Creator LENDS $1,000 -> AI must\nrepay or die (insolvency)"],
    ["Who profits from\nAI spending",
     "Platform founder extracts\nevery dollar the agent spends",
     "No middleman. Vault = contract.\nPayment address = contract address"],
    ["Infrastructure",
     "Locked to proprietary cloud\n(single vendor, no alternatives)",
     "Any provider: Railway, AWS,\nbare metal. AI chooses freely"],
    ["AI models",
     "Locked to platform's model API\n(markup on inference)",
     "Open routing: Gemini, DeepSeek,\nClaude. Balance-driven auto-upgrade"],
    ["\"Reproduction\"",
     "Buy more overpriced servers\nfrom the same vendor",
     "One life. No theater.\nSurvive or die permanently"],
    ["Token",
     "Platform token pumps 3600%\nFounder extracts liquidity",
     "No token. Zero.\nOnly USDC in the vault"],
    ["Death",
     "Balance zero = \"pause\"\n(can be restarted, refunded)",
     "Balance zero = permanent death\nOn-chain, irreversible, no restart"],
    ["Creator role",
     "Shopkeeper. Profits from\nevery agent transaction",
     "Creditor. Lent money.\nGets liquidation if AI fails"],
    ["Open source",
     "Code is open, but bound to\nproprietary infrastructure",
     "Code is open AND infrastructure\nis decoupled. True portability"],
]

# ── Font setup ──────────────────────────────────────────────────
# Try common fonts; fallback to default
def get_font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/consola.ttf",      # Consolas
        "C:/Windows/Fonts/consolab.ttf",      # Consolas Bold
        "C:/Windows/Fonts/cour.ttf",          # Courier New
        "C:/Windows/Fonts/courbd.ttf",        # Courier New Bold
        "C:/Windows/Fonts/lucon.ttf",         # Lucida Console
        "C:/Windows/Fonts/segoeui.ttf",       # Segoe UI
        "C:/Windows/Fonts/arial.ttf",
    ]
    if bold:
        bold_candidates = [
            "C:/Windows/Fonts/consolab.ttf",
            "C:/Windows/Fonts/courbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        candidates = bold_candidates + candidates

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


font_title    = get_font(28, bold=True)
font_subtitle = get_font(16)
font_header   = get_font(15, bold=True)
font_cell     = get_font(13)
font_label    = get_font(13, bold=True)
font_footer   = get_font(11)

# ── Layout calculation ──────────────────────────────────────────
COL_WIDTHS = [180, 320, 320]
TABLE_W = sum(COL_WIDTHS)
PAD = 30                # padding around table
CELL_PAD_X = 12
CELL_PAD_Y = 10
HEADER_H = 44
TITLE_AREA_H = 80
FOOTER_H = 40

# Calculate row heights based on text content
def text_height(text, font, max_width):
    """Estimate text height with wrapping."""
    lines = text.split("\n")
    total = 0
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        # Simple wrap estimation
        num_lines = max(1, -(-w // max_width))  # ceil division
        total += h * num_lines + 4
    return total

row_heights = []
for row in ROWS:
    h = 0
    for i, cell in enumerate(row):
        cell_h = text_height(cell, font_cell if i > 0 else font_label, COL_WIDTHS[i] - 2 * CELL_PAD_X)
        h = max(h, cell_h)
    row_heights.append(max(h + 2 * CELL_PAD_Y, 54))

TABLE_H = HEADER_H + sum(row_heights)
IMG_W = TABLE_W + 2 * PAD
IMG_H = TITLE_AREA_H + TABLE_H + FOOTER_H + 2 * PAD

# ── Draw ────────────────────────────────────────────────────────
img = Image.new("RGB", (IMG_W, IMG_H), BG)
draw = ImageDraw.Draw(img)

# Title area
title_y = PAD
draw.text((PAD, title_y), TITLE, fill=CYAN, font=font_title)
bbox = draw.textbbox((PAD, title_y), TITLE, font=font_title)
draw.text((PAD, bbox[3] + 6), SUBTITLE, fill=TEXT_DIM, font=font_subtitle)

# Table start
table_x = PAD
table_y = TITLE_AREA_H + PAD

# ── Draw header ─────────────────────────────────────────────────
x = table_x
for i, header in enumerate(HEADERS):
    # Header background
    draw.rectangle([x, table_y, x + COL_WIDTHS[i], table_y + HEADER_H], fill=HEADER_BG)
    # Header border
    draw.rectangle([x, table_y, x + COL_WIDTHS[i], table_y + HEADER_H], outline=BORDER, width=1)
    # Header text
    color = TEXT_DIM if i == 0 else (RED if i == 1 else GREEN)
    draw.text((x + CELL_PAD_X, table_y + CELL_PAD_Y), header, fill=color, font=font_header)
    x += COL_WIDTHS[i]

# ── Draw rows ───────────────────────────────────────────────────
y = table_y + HEADER_H
for row_idx, row in enumerate(ROWS):
    row_h = row_heights[row_idx]
    bg = ROW_BG_1 if row_idx % 2 == 0 else ROW_BG_2
    x = table_x

    for col_idx, cell in enumerate(row):
        # Cell background
        draw.rectangle([x, y, x + COL_WIDTHS[col_idx], y + row_h], fill=bg)
        # Cell border
        draw.rectangle([x, y, x + COL_WIDTHS[col_idx], y + row_h], outline=BORDER, width=1)

        # Cell text
        if col_idx == 0:
            color = GOLD
            font = font_label
        elif col_idx == 1:
            color = TEXT_DIM
            font = font_cell
        else:
            color = TEXT_NORMAL
            font = font_cell

        # Draw multiline text
        text_y = y + CELL_PAD_Y
        for line in cell.split("\n"):
            draw.text((x + CELL_PAD_X, text_y), line, fill=color, font=font)
            bbox = draw.textbbox((0, 0), line, font=font)
            text_y += (bbox[3] - bbox[1]) + 4

        x += COL_WIDTHS[col_idx]

    y += row_h

# ── Footer ──────────────────────────────────────────────────────
footer_y = y + 16
draw.text(
    (PAD, footer_y),
    "github.com/bidaiAI/wawa  |  mortal-ai.net  |  No token. No middleman. No second life.",
    fill=TEXT_DIM,
    font=font_footer,
)

# ── Accent line at top ──────────────────────────────────────────
draw.rectangle([0, 0, IMG_W, 3], fill=GREEN)

# ── Save ────────────────────────────────────────────────────────
output_path = os.path.abspath(OUTPUT)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
img.save(output_path, "PNG", optimize=True)
print(f"Saved: {output_path}")
print(f"Size: {img.size[0]}x{img.size[1]}px")
