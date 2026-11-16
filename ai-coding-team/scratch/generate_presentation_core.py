"""
Script to generate a presentation deck (.pptx) for the AI Coding Team project.
Includes widescreen 16:9 layout, embedded screenshots, metric cards, and slide speaker notes.
"""

import os
import pptx
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

# Initialize presentation
prs = pptx.Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank_layout = prs.slide_layouts[6]

# Color Palette Constants
BG_DARK = RGBColor(9, 13, 22)       # #090d16 Deep space navy
BG_CARD = RGBColor(19, 28, 46)      # #131c2e Card background
BG_CARD_LIGHT = RGBColor(30, 41, 59) # #1e293b Secondary card
BORDER_COLOR = RGBColor(51, 65, 85) # #334155 Subtle border
TEXT_WHITE = RGBColor(248, 250, 252) # #f8fafc Crisp white text
TEXT_MUTED = RGBColor(148, 163, 184) # #94a3b8 Muted slate
TEXT_SUB = RGBColor(203, 213, 225)   # #cbd5e1 Sub text
ACCENT_INDIGO = RGBColor(99, 102, 241) # #6366f1 Primary brand
ACCENT_CYAN = RGBColor(6, 182, 212)    # #06b6d4 Secondary cyan
ACCENT_EMERALD = RGBColor(16, 185, 129)# #10b981 Success / Metric green
ACCENT_AMBER = RGBColor(245, 158, 11)  # #f59e0b Warning / Accent
ACCENT_PURPLE = RGBColor(168, 85, 247) # #a855f7 Vibrant purple

MEDIA_DIR = r"C:\Users\amohd\.gemini\antigravity\brain\13bee21d-daf8-42f3-a885-e1216c31eff8\.user_uploaded"
IMG_DASHBOARD = os.path.join(MEDIA_DIR, "media_1794815231764_47e8db70.jpg")
IMG_EXECUTION = os.path.join(MEDIA_DIR, "media_1794560652603_fbcb97e3.jpg")
IMG_CODE_EXPLORER = os.path.join(MEDIA_DIR, "media_1794813551893_631bd87a.png")
IMG_BUILD_COMPLETE = os.path.join(MEDIA_DIR, "media_1794550950075_219a642c.png")


def create_base_slide(badge_text="PROJECT PRESENTATION", title_text="", subtitle_text=""):
    """Creates a base slide with dark tech background, category badge, and title."""
    slide = prs.slides.add_slide(blank_layout)
    
    # 1. Dark Background
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG_DARK
    bg.line.fill.background()
    
    # 2. Header Category Badge
    if badge_text:
        badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.45), Inches(3.2), Inches(0.38))
        badge.fill.solid()
        badge.fill.fore_color.rgb = RGBColor(24, 34, 56)
        badge.line.color.rgb = ACCENT_INDIGO
        badge.line.width = Pt(1)
        tf = badge.text_frame
        tf.text = badge_text.upper()
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = ACCENT_CYAN
        
    # 3. Main Title
    if title_text:
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.85), Inches(11.5), Inches(0.8))
        tf = title_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
        
        # Subtitle
        if subtitle_text:
            p2 = tf.add_paragraph()
            p2.text = subtitle_text
            p2.font.size = Pt(13)
            p2.font.color.rgb = TEXT_MUTED
            p2.space_before = Pt(4)
            
    return slide


def add_card(slide, left, top, width, height, title="", border_color=BORDER_COLOR, bg_color=BG_CARD):
    """Draws a rounded container card."""
    card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    card.fill.solid()
    card.fill.fore_color.rgb = bg_color
    card.line.color.rgb = border_color
    card.line.width = Pt(1)
    
    if title:
        tb = slide.shapes.add_textbox(left + Inches(0.2), top + Inches(0.18), width - Inches(0.4), Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = TEXT_WHITE
    return card


def set_speaker_notes(slide, notes_text):
    """Sets speaker notes for presentation mode."""
    slide.notes_slide.notes_text_frame.text = notes_text.strip()


print("Base presentation generator loaded.")
