"""Convert HOW-TO-RUN.md to a clean plain PDF using fpdf2."""
from fpdf import FPDF
from pathlib import Path
import re

md_path = Path(__file__).parent / "HOW-TO-RUN.md"
pdf_path = Path(__file__).parent / "HOW-TO-RUN.pdf"

lines = md_path.read_text(encoding="utf-8").splitlines()

# ── helpers ──────────────────────────────────────────────────────────────────

def to_ascii(text):
    """Replace Unicode characters that Helvetica can't render."""
    chars = {
        "→": "->", "←": "<-", "•": "-",
        "–": "-",  "—": "--", "…": "...",
        "‘": "'",  "’": "'",  "“": '"', "”": '"',
        "·": ".",  "✓": "OK", "✔": "OK",
        "✅": "[OK]",
    }
    for ch, rep in chars.items():
        text = text.replace(ch, rep)
    return text.encode("latin-1", errors="replace").decode("latin-1")

def strip_markup(text):
    """Remove markdown bold/italic/code/link markers."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"`(.+?)`",        r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1  (\2)", text)
    text = re.sub(r"^> ", "",        text)
    return to_ascii(text)

# ── PDF setup ────────────────────────────────────────────────────────────────

LM, RM, TM = 20, 20, 20   # left / right / top margins (mm)
PW = 210 - LM - RM        # usable page width

class Doc(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

pdf = Doc()
pdf.add_page()
pdf.set_margins(LM, TM, RM)
pdf.set_auto_page_break(auto=True, margin=16)

# ── rendering helpers ────────────────────────────────────────────────────────

def write_line(text, font="Helvetica", style="", size=10, color=(30, 30, 30),
               indent=0, line_h=6, fill_color=None, border=0):
    pdf.set_left_margin(LM + indent)
    pdf.set_x(LM + indent)
    pdf.set_font(font, style, size)
    pdf.set_text_color(*color)
    if fill_color:
        pdf.set_fill_color(*fill_color)
    w = PW - indent
    pdf.multi_cell(w, line_h, strip_markup(text),
                   border=border, fill=bool(fill_color))
    pdf.set_left_margin(LM)

# ── parse and render ─────────────────────────────────────────────────────────

in_code = False
code_buf = []

for raw in lines:
    # ── code block ──
    if raw.strip().startswith("```"):
        if not in_code:
            in_code = True
            code_buf = []
        else:
            in_code = False
            block = "\n".join(code_buf)
            pdf.set_left_margin(LM)
            pdf.set_x(LM)
            pdf.set_font("Courier", size=8.5)
            pdf.set_text_color(30, 30, 30)
            pdf.set_fill_color(245, 245, 245)
            pdf.set_draw_color(210, 210, 210)
            pdf.multi_cell(PW, 5, to_ascii(block),
                           border=1, fill=True, padding=(4, 6, 4, 6))
            pdf.ln(2)
        continue

    if in_code:
        code_buf.append(raw)
        continue

    # ── H1 ──
    if re.match(r"^# [^#]", raw):
        text = raw[2:]
        pdf.ln(2)
        write_line(text, style="B", size=18, color=(10, 10, 10), line_h=10)
        y = pdf.get_y() + 1
        pdf.set_draw_color(10, 10, 10)
        pdf.set_line_width(0.5)
        pdf.line(LM, y, LM + PW, y)
        pdf.ln(6)

    # ── H2 ──
    elif re.match(r"^## ", raw):
        pdf.ln(3)
        write_line(raw[3:], style="B", size=12, color=(10, 10, 10), line_h=7)
        pdf.ln(2)

    # ── HR ──
    elif raw.strip() == "---":
        pdf.set_draw_color(210, 210, 210)
        pdf.set_line_width(0.3)
        pdf.line(LM, pdf.get_y() + 1, LM + PW, pdf.get_y() + 1)
        pdf.ln(4)

    # ── blockquote ──
    elif raw.startswith("> "):
        write_line(raw[2:], style="I", size=10,
                   color=(40, 80, 160), fill_color=(235, 243, 255),
                   indent=2, line_h=6)
        pdf.ln(2)

    # ── numbered list ──
    elif re.match(r"^\d+\. ", raw):
        num, rest = raw.split(". ", 1)
        write_line(f"{num}.  {rest}", size=10, indent=4, line_h=6)

    # ── bullet ──
    elif re.match(r"^[-*] ", raw):
        write_line(f"  -  {raw[2:]}", size=10, indent=4, line_h=6)

    # ── blank ──
    elif raw.strip() == "":
        pdf.ln(2)

    # ── paragraph ──
    else:
        write_line(raw, size=10, line_h=6)

pdf.output(str(pdf_path))
print(f"PDF saved -> {pdf_path}")
