"""Styling for the Streamlit app.

Kept out of app.py because it's 200 lines of CSS and it was drowning the logic.
Design notes: this is a bedtime product, so the palette is night-time and the
contrast is deliberately soft - a bright white page at 8pm is the wrong tool.
"""
# Google Fonts over CDN. Works offline-ish (falls back to Georgia/system) but
# it's an external request on every load. Would self-host for production.
FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
"""
CSS = """
<style>
  :root {
    --ink:      #eef1ff;
    --ink-dim:  #98a2cf;
    --ink-faint:#6b76a8;
    --panel:    rgba(255,255,255,.045);
    --panel-2:  rgba(255,255,255,.075);
    --line:     rgba(255,255,255,.09);
    --gold:     #ffd39b;
    --good:     #7ee8b0;
    --warn:     #ffd166;
    --bad:      #ff9b9b;
  }

  .stApp {
    background:
      radial-gradient(1100px 620px at 12% -8%, #23305e 0%, transparent 58%),
      radial-gradient(900px 520px at 88% 4%, #3a2a55 0%, transparent 52%),
      linear-gradient(180deg, #0b1024 0%, #141a35 100%);
    background-attachment: fixed;
  }
  .block-container { padding-top: 2.2rem; max-width: 1180px; }

  html, body, [class*="css"], .stMarkdown, p, span, div, label {
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
    color: var(--ink);
  }
  h1, h2, h3, h4 { font-family: 'Fraunces', Georgia, serif !important; color: var(--ink) !important; }
  h1 { font-weight: 600 !important; letter-spacing: -.5px; }

  /* masthead */
  .masthead { padding: 6px 0 22px 0; }
  .masthead h1 { font-size: 2.5rem; margin: 0 0 4px 0; }
  .masthead .sub { color: var(--ink-dim); font-size: 15px; }

  /* covers */
  .cover-wrap {
    position: relative; border-radius: 16px; overflow: hidden;
    border: 1px solid var(--line);
    box-shadow: 0 10px 30px rgba(0,0,0,.5);
    transition: transform .22s cubic-bezier(.2,.8,.3,1), box-shadow .22s ease;
    margin-bottom: 10px;
  }
  .cover-wrap:hover { transform: translateY(-4px); box-shadow: 0 18px 44px rgba(0,0,0,.66); }
  .cover-wrap img { width: 100%; height: auto; display: block; }
  .cover-lg { border-radius: 20px; box-shadow: 0 20px 54px rgba(0,0,0,.6); }

  /* chips + meta */
  .chip {
    display: inline-block; padding: 3px 11px; border-radius: 999px;
    font-size: 11px; font-weight: 500; letter-spacing: .3px;
    background: var(--panel-2); color: #d5dbff; border: 1px solid var(--line);
    margin-right: 6px;
  }
  .chip-quiet { background: transparent; color: var(--ink-faint); }
  .meta { color: var(--ink-faint); font-size: 12.5px; margin: 2px 0 10px 0; }
  .card-title {
    font-family: 'Fraunces', Georgia, serif; font-size: 17px; font-weight: 600;
    margin: 2px 0 3px 0; line-height: 1.3;
  }

  /* the reading page */
  .reader {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 20px; padding: 40px 46px 34px 46px;
  }
  .story-text {
    font-family: 'Fraunces', Georgia, serif;
    font-size: 20px; line-height: 1.9; color: #f2f4ff;
    max-width: 40rem; margin: 0 auto;
  }
  .story-text p { margin: 0 0 1.25em 0; }
  .story-text p:first-of-type::first-letter {
    font-size: 3.1em; float: left; line-height: .84;
    padding: 6px 10px 0 0; color: var(--gold); font-weight: 600;
  }
  .story-title {
    font-family: 'Fraunces', Georgia, serif; font-size: 2.05rem;
    text-align: center; margin: 0 0 6px 0; line-height: 1.2;
  }
  .story-sub { text-align:center; color: var(--ink-faint); font-size: 13px;
               margin-bottom: 30px; }

  /* how-you-want-it picker */
  .picker { display:flex; gap:12px; margin: 6px 0 18px 0; }

  /* section headers */
  .section { display:flex; align-items:baseline; gap:12px; margin: 26px 0 10px 0; }
  .section h3 { margin:0; font-size: 1.25rem; }
  .section .hint { color: var(--ink-faint); font-size: 13px; }

  /* buttons */
  .stButton > button {
    border-radius: 11px; border: 1px solid var(--line);
    background: var(--panel-2); color: var(--ink); font-weight: 500;
    transition: all .16s ease; padding: .5rem 1rem;
  }
  .stButton > button:hover {
    background: rgba(255,255,255,.13); border-color: rgba(255,255,255,.24);
    transform: translateY(-1px); color: var(--ink);
  }
  .stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#7b6bd6,#a385e8); border: none; color: #fff;
  }
  .stButton > button[kind="primary"]:hover { filter: brightness(1.1); }

  /* inputs */
  .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
    background: rgba(255,255,255,.05) !important; color: var(--ink) !important;
    border: 1px solid var(--line) !important; border-radius: 11px !important;
  }
  .stTextArea textarea { font-size: 15px !important; }

  /* tabs */
  .stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--line); }
  .stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 10px 10px 0 0; padding: 9px 18px;
    color: var(--ink-dim); font-weight: 500;
  }
  .stTabs [aria-selected="true"] { background: var(--panel-2); color: var(--ink) !important; }

  /* metrics */
  [data-testid="stMetric"] {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 13px; padding: 13px 15px;
  }
  [data-testid="stMetricLabel"] { color: var(--ink-faint) !important; font-size: 11.5px !important; }
  [data-testid="stMetricValue"] { font-size: 1.5rem !important; }

  /* progress bars in the rubric */
  .stProgress > div > div > div { background: linear-gradient(90deg,#7b6bd6,#a385e8); }

  /* audio */
  audio { width: 100%; border-radius: 10px; margin-top: 6px; }

  /* sidebar */
  section[data-testid="stSidebar"] {
    background: rgba(8,12,28,.82); border-right: 1px solid var(--line);
  }
  section[data-testid="stSidebar"] .stMarkdown { font-size: 13.5px; }

  /* misc */
  hr, .stDivider { border-color: var(--line) !important; }
  .stExpander { border: 1px solid var(--line) !important; border-radius: 13px !important;
                background: var(--panel) !important; }
  .footer { color: var(--ink-faint); font-size: 12px; text-align:center;
            padding: 34px 0 12px 0; }
  #MainMenu, footer { visibility: hidden; }
</style>
"""

def inject(st):
    st.markdown(FONTS + CSS, unsafe_allow_html=True)
