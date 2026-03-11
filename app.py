import streamlit as st
import boto3
import json
import uuid
import re
import os
from datetime import datetime
from botocore.exceptions import ClientError

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NBA Assistant - Rulebook & CBA",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# THEME CONFIG
# ─────────────────────────────────────────────
THEMES = {
    "rulebook": {
        "name": "🏀 NBA Rulebook",
        "kb_id": "JFEGBVQF3O",
        "primary_color": "#F58426",
        "secondary_color": "#1A1A1A",
        "gradient_start": "#F58426",
        "gradient_end": "#FF6B35",
        "title": "🏀 NBA Rulebook Chatbot",
        "subtitle": "📖 Ask questions about NBA rules and regulations",
        "icon": "🏀",
        "examples": [
            "What constitutes a traveling violation?",
            "How long is a shot clock in the NBA?",
            "What are the rules for goaltending?",
            "What's the difference between a foul and a violation?",
        ],
    },
    "cba": {
        "name": "💰 CBA & Salary Cap",
        "kb_id": "B902HDGE8W",
        "primary_color": "#2E7D32",
        "secondary_color": "#FFD700",
        "gradient_start": "#2E7D32",
        "gradient_end": "#4CAF50",
        "title": "💰 NBA CBA & Salary Cap Assistant",
        "subtitle": "💵 Ask questions about contracts, salary cap, and league rules",
        "icon": "💰",
        "examples": [
            "What's a restricted free agent?",
            "What rules are there around team options?",
            "When can teams claim a waived player?",
            "How does the salary cap work?",
        ],
    },
}

MODE_KEYS = tuple(THEMES.keys())
DEFAULT_MODEL_ARNS = {
    "rulebook": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "cba": "us.anthropic.claude-opus-4-20250514-v1:0",
}
DEFAULT_QUIZ_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# ─────────────────────────────────────────────
# CBA SOURCE IDENTIFICATION
# ─────────────────────────────────────────────
CBA_SOURCE_PATTERNS = {
    "cba": ["cba", "collective-bargaining", "collective_bargaining", "labor-agreement", "labor_agreement"],
    "operations": ["operations", "ops-manual", "operations-manual", "basketball-operations", "ops_manual"],
}

def identify_cba_source(uri: str):
    """
    Identify whether a CBA citation comes from the CBA document or the Operations Manual.
    Returns (badge_label, css_class, display_name).
    """
    uri_lower = uri.lower()
    filename = uri.split("/")[-1] if "/" in uri else uri
    display_name = re.sub(r"[-_]", " ", filename.replace(".pdf", "")).title()

    for source_type, patterns in CBA_SOURCE_PATTERNS.items():
        if any(p in uri_lower for p in patterns):
            if source_type == "cba":
                return "📜 CBA Document", "source-cba", "CBA"
            else:
                return "📋 Operations Manual", "source-operations", "Operations Manual"

    # Fallback: use the cleaned filename
    return f"📄 {display_name}", "source-unknown", display_name


# ─────────────────────────────────────────────
# CROSS-MODE DETECTION
# ─────────────────────────────────────────────
CROSS_MODE_KEYWORDS = {
    "rulebook_to_cba": [
        "salary", "contract", "cap space", "waive", "waived", "suspension",
        "suspended", "fine", "fined", "trade", "free agent", "buyout",
        "incentive", "guaranteed", "minimum salary", "maximum salary",
    ],
    "cba_to_rulebook": [
        "technical foul", "flagrant foul", "ejection", "ejected", "violation",
        "traveling", "goaltending", "shot clock", "game clock", "referee",
        "official", "out of bounds", "possession", "foul out",
    ],
}

def detect_cross_mode(response_text: str, current_mode: str):
    """Return the other mode name if cross-mode topics are detected, else None."""
    text_lower = response_text.lower()
    key = "rulebook_to_cba" if current_mode == "rulebook" else "cba_to_rulebook"
    matches = [kw for kw in CROSS_MODE_KEYWORDS[key] if kw in text_lower]
    if len(matches) >= 2:
        return "cba" if current_mode == "rulebook" else "rulebook"
    return None


# ─────────────────────────────────────────────
# CONFIDENCE LEVEL
# ─────────────────────────────────────────────
def get_confidence(citations: list):
    """Return (label, hex_color) confidence indicator based on citation quality."""
    if not citations:
        return "⚠️ Low", "#FF9800"
    with_meta = sum(1 for c in citations if c.get("metadata"))
    if len(citations) >= 3 and with_meta >= 2:
        return "✅ High", "#4CAF50"
    elif len(citations) >= 2:
        return "🟡 Medium", "#FFC107"
    return "🟠 Low", "#FF9800"


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
def _empty_quiz_state():
    return {
        "current": None,
        "raw": None,
        "show_answer": False,
    }


def init_session_state():
    defaults = {
        "mode": "rulebook",
        "dark_mode": False,
        "session_ids": {mode: None for mode in MODE_KEYS},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    current_mode = st.session_state.mode

    if "messages_by_mode" not in st.session_state:
        legacy_messages = st.session_state.get("messages", [])
        st.session_state.messages_by_mode = {
            mode: list(legacy_messages) if mode == current_mode else []
            for mode in MODE_KEYS
        }
    else:
        for mode in MODE_KEYS:
            st.session_state.messages_by_mode.setdefault(mode, [])

    for mode in MODE_KEYS:
        st.session_state.session_ids.setdefault(mode, None)

    if "pending_prompts" not in st.session_state:
        legacy_prompt = st.session_state.get("pending_prompt")
        st.session_state.pending_prompts = {
            mode: legacy_prompt if mode == current_mode else None
            for mode in MODE_KEYS
        }
    else:
        for mode in MODE_KEYS:
            st.session_state.pending_prompts.setdefault(mode, None)

    if "quiz_state" not in st.session_state:
        st.session_state.quiz_state = {mode: _empty_quiz_state() for mode in MODE_KEYS}
        if any(k in st.session_state for k in ("current_quiz", "quiz_raw", "show_quiz_answer")):
            st.session_state.quiz_state[current_mode] = {
                "current": st.session_state.get("current_quiz"),
                "raw": st.session_state.get("quiz_raw"),
                "show_answer": st.session_state.get("show_quiz_answer", False),
            }
    else:
        for mode in MODE_KEYS:
            st.session_state.quiz_state.setdefault(mode, _empty_quiz_state())

    if "quiz_asked" not in st.session_state:
        st.session_state.quiz_asked = {mode: {} for mode in MODE_KEYS}
    else:
        for mode in MODE_KEYS:
            st.session_state.quiz_asked.setdefault(mode, {})


def get_messages(mode: str = None):
    mode = mode or st.session_state.mode
    return st.session_state.messages_by_mode[mode]


def get_quiz_state(mode: str = None):
    mode = mode or st.session_state.mode
    return st.session_state.quiz_state[mode]


def reset_quiz_state(mode: str = None):
    mode = mode or st.session_state.mode
    st.session_state.quiz_state[mode] = _empty_quiz_state()


def get_quiz_history(mode: str, topic: str):
    topic_history = st.session_state.quiz_asked.setdefault(mode, {})
    return topic_history.setdefault(topic, [])


def clear_mode_state(mode: str):
    st.session_state.messages_by_mode[mode] = []
    st.session_state.session_ids[mode] = None
    st.session_state.pending_prompts[mode] = None
    st.session_state.quiz_asked[mode] = {}
    reset_quiz_state(mode)

init_session_state()


# ─────────────────────────────────────────────
# DYNAMIC CSS
# ─────────────────────────────────────────────
def build_css(theme: dict, dark: bool) -> str:
    bg           = "#1A1A2E" if dark else "#f5f5f5"
    surface      = "#16213E" if dark else "#ffffff"
    text         = "#E0E0E0" if dark else "#1A1A1A"
    sub_text     = "#aaaaaa" if dark else theme["primary_color"]
    chat_bg      = "#0F3460" if dark else "#f8f9fa"
    excerpt_bg   = "#1a2a3a" if dark else "linear-gradient(135deg,#FFF8F0 0%,#FFE4D1 100%)"
    excerpt_text = "#E0E0E0" if dark else "#2c3e50"
    p            = theme["primary_color"]
    s            = theme["secondary_color"]

    return f"""
<style>
/* ── Base ─────────────────────────────── */
.stApp {{ background-color: {bg} !important; }}
.main  {{ background-color: {bg} !important; padding: 2rem; }}

/* ── Typography ───────────────────────── */
h1,h2,h3 {{ color: {text} !important; }}
.subtitle {{ color: {sub_text}; font-size:1.1rem; font-weight:600; }}

/* ── Global text fill (Safari/iOS) ────── */
p, span, li, .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown li {{
    color: {text} !important;
    -webkit-text-fill-color: {text} !important;
}}

/* ── Chat messages ─────────────────────── */
.stChatMessage {{
    background-color: {chat_bg} !important;
    border-radius: 10px;
    padding: 1rem;
    margin-bottom: 1rem;
    border-left: 4px solid {p};
    word-wrap: break-word;
}}
.stChatMessage p,
.stChatMessage div,
.stChatMessage span,
.stChatMessage li {{
    color: {text} !important;
    -webkit-text-fill-color: {text} !important;
}}

/* ── Timestamp ─────────────────────────── */
.msg-ts {{
    font-size: 0.7rem;
    color: #888;
    text-align: right;
    margin-top: 0.3rem;
}}

/* ── Source type badges ────────────────── */
.source-type-badge {{
    display: inline-block;
    padding: 0.3rem 0.7rem;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 700;
    margin-right: 0.4rem;
    margin-bottom: 0.5rem;
    letter-spacing: 0.3px;
}}
.source-cba        {{ background: #1565C0; color: white; }}
.source-operations {{ background: #6A1B9A; color: white; }}
.source-unknown    {{ background: #37474F; color: white; }}

/* ── Rule / location badge ─────────────── */
.rule-location {{
    display: inline-block;
    background: linear-gradient(135deg, {s} 0%, {p} 100%);
    color: white;
    padding: 0.35rem 0.75rem;
    border-radius: 6px;
    font-size: 0.82rem;
    font-weight: 700;
    margin-right: 0.4rem;
    margin-bottom: 0.5rem;
    border: 2px solid {p};
    text-transform: uppercase;
    letter-spacing: 0.4px;
}}

/* ── Confidence badge ──────────────────── */
.conf-badge {{
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 12px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}}

/* ── Source excerpt ────────────────────── */
.source-excerpt {{
    background: {excerpt_bg};
    padding: 1rem 1.5rem;
    border-radius: 8px;
    margin: 0.4rem 0 0.8rem 0;
    border-left: 3px solid {p};
    color: {excerpt_text} !important;
    -webkit-text-fill-color: {excerpt_text} !important;
    font-size: 0.93rem;
    line-height: 1.6;
    box-shadow: 0 2px 4px rgba(0,0,0,0.06);
    word-wrap: break-word;
}}

/* ── Cross-mode suggestion ─────────────── */
.cross-mode-box {{
    background: linear-gradient(135deg,#1565C0 0%,#42A5F5 100%);
    color: white !important;
    -webkit-text-fill-color: white !important;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-top: 0.75rem;
    font-size: 0.9rem;
}}
.cross-mode-box p,
.cross-mode-box span {{
    color: white !important;
    -webkit-text-fill-color: white !important;
}}

/* ── Welcome example buttons ───────────── */
div[data-testid="stButton"] button[kind="secondary"] {{
    border: 2px solid {p};
    border-radius: 8px;
    background: {surface};
    color: {text};
    text-align: left;
    transition: all 0.2s ease;
}}
div[data-testid="stButton"] button[kind="secondary"]:hover {{
    background: {p}22;
    border-color: {p};
}}

/* ── Metric card ───────────────────────── */
.metric-card {{
    background: linear-gradient(135deg, {theme["gradient_start"]} 0%, {theme["gradient_end"]} 100%);
    padding: 1rem;
    border-radius: 10px;
    color: white;
    text-align: center;
    box-shadow: 0 3px 6px rgba(0,0,0,0.15);
    margin: 0.4rem 0;
}}
.metric-card h2, .metric-card p {{ color: white !important; margin: 0; }}

/* ── Sidebar ───────────────────────────── */
[data-testid="stSidebar"] {{
    background-color: {surface} !important;
}}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {{
    color: {text} !important;
    -webkit-text-fill-color: {text} !important;
}}

/* ── Chat input ────────────────────────── */
.stChatInputContainer textarea,
.stChatInputContainer input,
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] input,
[data-baseweb="textarea"] textarea {{
    color: {text} !important;
    -webkit-text-fill-color: {text} !important;
    background-color: {surface} !important;
    opacity: 1 !important;
}}
textarea::placeholder, input::placeholder {{
    color: #777 !important;
    -webkit-text-fill-color: #777 !important;
    opacity: 1 !important;
}}

/* ── Loading animation ─────────────────── */
@keyframes bounce {{
    0%, 80%, 100% {{ transform: translateY(0) rotate(0deg); }}
    40%            {{ transform: translateY(-18px) rotate(20deg); }}
    60%            {{ transform: translateY(-8px) rotate(-10deg); }}
}}
@keyframes pulse-ring {{
    0%   {{ transform: scale(0.8); opacity: 0.6; }}
    50%  {{ transform: scale(1.1); opacity: 0.2; }}
    100% {{ transform: scale(0.8); opacity: 0.6; }}
}}
@keyframes fade-dots {{
    0%,20%  {{ opacity: 0; }}
    50%      {{ opacity: 1; }}
    80%,100% {{ opacity: 0; }}
}}
.loading-card {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem 1rem;
    border-radius: 12px;
    background: {surface};
    border: 1px solid {p}44;
    box-shadow: 0 4px 16px rgba(0,0,0,0.12);
    margin: 0.5rem 0;
    text-align: center;
}}
.loading-ball {{
    font-size: 3rem;
    animation: bounce 1.2s ease-in-out infinite;
    display: inline-block;
    margin-bottom: 0.5rem;
    filter: drop-shadow(0 6px 8px rgba(0,0,0,0.25));
}}
.loading-ring {{
    width: 60px;
    height: 8px;
    background: {p}44;
    border-radius: 50%;
    animation: pulse-ring 1.2s ease-in-out infinite;
    margin: 0 auto 1.2rem auto;
}}
.loading-label {{
    font-size: 1.05rem;
    font-weight: 600;
    color: {p} !important;
    -webkit-text-fill-color: {p} !important;
    margin-bottom: 0.4rem;
}}
.loading-sub {{
    font-size: 0.82rem;
    color: #888 !important;
    -webkit-text-fill-color: #888 !important;
}}
.loading-dots span {{
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: {p};
    margin: 0 3px;
    animation: fade-dots 1.4s ease-in-out infinite;
}}
.loading-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
.loading-dots span:nth-child(3) {{ animation-delay: 0.4s; }}

/* ── Stray Streamlit chrome ────────────── */
footer {{ display: none !important; }}

/* ── Responsive ────────────────────────── */
@media (max-width: 768px) {{
    .main {{ padding: 1rem !important; padding-bottom: 100px !important; }}
    h1    {{ font-size: 1.4rem !important; }}
}}
</style>
"""

st.markdown(build_css(THEMES[st.session_state.mode], st.session_state.dark_mode), unsafe_allow_html=True)

# Auto-scroll JS (mobile)
st.markdown("""
<script>
function scrollToBottom(){
  if(window.innerWidth<=768){
    setTimeout(()=>window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'}),120);
  }
}
const obs=new MutationObserver(()=>scrollToBottom());
window.addEventListener('load',()=>{
  const n=document.querySelector('.main');
  if(n) obs.observe(n,{childList:true,subtree:true});
  scrollToBottom();
});
</script>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# RUNTIME CONFIG
# ─────────────────────────────────────────────
def _secret_section(name: str):
    return st.secrets[name] if name in st.secrets else {}


def _section_get(section, key: str, default=None):
    try:
        if key in section:
            return section[key]
    except TypeError:
        return default
    return default


def _secret_value(key: str, default=None):
    return st.secrets[key] if key in st.secrets else default


def get_aws_region():
    aws = _secret_section("aws")
    return (
        _section_get(aws, "region")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def get_mode_runtime_config(mode: str) -> dict:
    theme = THEMES[mode]
    knowledge_bases = _secret_section("knowledge_bases")
    models = _secret_section("models")
    kb_secret_key = "knowledge_base_id" if mode == "rulebook" else "cba_knowledge_base_id"
    kb_env_key = "RULEBOOK_KB_ID" if mode == "rulebook" else "CBA_KB_ID"
    model_env_key = "RULEBOOK_MODEL_ARN" if mode == "rulebook" else "CBA_MODEL_ARN"

    return {
        "kb_id": (
            _section_get(knowledge_bases, f"{mode}_id")
            or _secret_value(kb_secret_key)
            or os.getenv(kb_env_key)
            or theme["kb_id"]
        ),
        "model_arn": (
            _section_get(models, f"{mode}_model_arn")
            or _secret_value(f"{mode}_model_arn")
            or os.getenv(model_env_key)
            or DEFAULT_MODEL_ARNS[mode]
        ),
        "quiz_model_id": (
            _section_get(models, "quiz_model_id")
            or _secret_value("quiz_model_id")
            or os.getenv("QUIZ_MODEL_ID")
            or DEFAULT_QUIZ_MODEL_ID
        ),
        "region": get_aws_region(),
    }


def get_boto_client_kwargs(region_name: str = None) -> dict:
    aws = _secret_section("aws")
    region = region_name or get_aws_region()
    access_key = _section_get(aws, "access_key_id")
    secret_key = _section_get(aws, "secret_access_key")
    session_token = _section_get(aws, "session_token")

    kwargs = {"region_name": region}
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return kwargs


# ─────────────────────────────────────────────
# AWS BEDROCK CLIENT
# ─────────────────────────────────────────────
@st.cache_resource
def get_bedrock_client(service_name: str, region_name: str = None):
    try:
        return boto3.client(service_name=service_name, **get_boto_client_kwargs(region_name))
    except Exception as e:
        st.error(f"⚠️ Error initialising {service_name} client: {e}")
        return None


@st.cache_resource
def get_bedrock_runtime_client(region_name: str = None):
    """Direct model invocation client — used for quiz generation (no RAG needed)."""
    return get_bedrock_client("bedrock-runtime", region_name)


# ─────────────────────────────────────────────
# CITATION RENDERING (single helper – no duplication)
# ─────────────────────────────────────────────
def render_citations(citations: list, mode: str):
    """Deduplicate, badge, and render citations for any mode."""
    if not citations:
        return

    # ── Safety-net dedup (primary dedup happens in _extract_citations) ──
    seen, unique = set(), []
    for c in citations:
        fp = c.get("content", "").strip()[:150]
        if fp not in seen:
            seen.add(fp)
            unique.append(c)

    # ── Confidence indicator ──
    conf_label, conf_color = get_confidence(unique)
    st.markdown(
        f'<span class="conf-badge" style="background:{conf_color}22;color:{conf_color};'
        f'border:1px solid {conf_color};">Confidence: {conf_label}</span>',
        unsafe_allow_html=True,
    )

    for citation in unique:
        content  = citation.get("content", "No content available")
        metadata = citation.get("metadata", {})
        uri      = citation.get("uri", "")

        badge_html = ""

        # ── CBA source-document badge (CBA mode only) ──
        if mode == "cba":
            badge_label, css_cls, doc_name = identify_cba_source(uri)
            badge_html += f'<span class="source-type-badge {css_cls}">{badge_label}</span>'

        # ── Location / rule metadata badge ──
        loc_parts = [
            f"{k.title()} {metadata[k]}"
            for k in ["rule", "section", "article", "part", "subsection", "page"]
            if k in metadata
        ]
        if loc_parts:
            badge_html += f'<span class="rule-location">📍 {", ".join(loc_parts)}</span>'

        if badge_html:
            st.markdown(f'<div style="margin-bottom:0.3rem">{badge_html}</div>', unsafe_allow_html=True)

        # ── Excerpt preview ──
        preview = (content[:200] + "…") if len(content) > 200 else content
        st.markdown(
            f'<div class="source-excerpt">{preview.replace("$", r"$")}</div>',
            unsafe_allow_html=True,
        )

        # ── Full text expander ──
        if len(content) > 200:
            with st.expander("📖 Read full excerpt"):
                st.markdown(f"_{content.replace('$', r'$')}_")

        # ── Copy source text ──
        with st.expander("📋 Copy source text"):
            st.code(content, language=None)

        st.markdown("")


# ─────────────────────────────────────────────
# KNOWLEDGE BASE QUERY
# ─────────────────────────────────────────────
def _extract_citations(response: dict) -> list:
    """Extract and deduplicate citations at source so stored messages are already clean."""
    raw = []
    for cit in response.get("citations", []):
        for ref in cit.get("retrievedReferences", []):
            s3 = ref.get("location", {}).get("s3Location", {})
            raw.append({
                "content":  ref.get("content", {}).get("text", ""),
                "uri":      s3.get("uri", "Unknown source"),
                "metadata": ref.get("metadata", {}),
            })

    # Deduplicate: primary key = first 150 chars of content; secondary = base URI (no fragment)
    seen_content, seen_uri, unique = set(), set(), []
    for c in raw:
        text        = c["content"].strip()
        fingerprint = text[:150]
        base_uri    = c["uri"].split("#")[0]          # strip chunk fragment e.g. #chunk-3

        if fingerprint and fingerprint in seen_content:
            continue
        if not fingerprint and base_uri in seen_uri:
            continue

        seen_content.add(fingerprint)
        seen_uri.add(base_uri)
        # Normalise empty content
        if not text:
            c["content"] = "No content available"
        unique.append(c)

    return unique


# ─────────────────────────────────────────────
# CITATION RELEVANCE FILTER
# ─────────────────────────────────────────────
# Words that carry no signal for relevance matching
_STOPWORDS = {
    "a","an","the","is","are","was","were","be","been","being","have","has","had",
    "do","does","did","will","would","could","should","may","might","shall","can",
    "not","no","nor","so","yet","both","either","neither","each","few","more",
    "most","other","some","such","than","then","that","this","these","those",
    "what","which","who","whom","how","when","where","why","and","but","or","for",
    "in","on","at","to","of","with","by","from","as","into","through","during",
    "between","about","against","before","after","above","below","up","down","out",
    "off","over","under","again","further","once","any","all","both","there","here",
    "if","its","it","it's","them","they","their","our","us","we","you","your","i",
    "he","she","his","her","him","my","me","rules","rule","nba","shall","player",
    "team","game","ball","court","play","players","teams",
}

def _score_citation(citation: dict, question: str) -> float:
    """
    Score a citation's relevance.
    Uses keyword overlap between the citation and the user's question.
    Returns a float 0-1.  Higher = more relevant.
    """
    def keywords(text: str) -> set:
        tokens = re.findall(r"[a-z]+", text.lower())
        return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}

    q_kw = keywords(question)
    if not q_kw:
        return 0.0

    metadata = " ".join(f"{k} {v}" for k, v in citation.get("metadata", {}).items())
    cit_kw = keywords(f"{citation.get('content', '')} {metadata} {citation.get('uri', '')}")

    if not cit_kw:
        return 0.0

    overlap_score = len(cit_kw & q_kw) / len(q_kw)
    phrase_bonus = 0.0

    question_lower = question.lower()
    content_lower = citation.get("content", "").lower()
    uri_lower = citation.get("uri", "").lower()
    for phrase in re.findall(r"[a-z]+(?:\s+[a-z]+)+", question_lower):
        if len(phrase.split()) >= 2 and (phrase in content_lower or phrase in uri_lower):
            phrase_bonus = max(phrase_bonus, 0.15)

    return min(overlap_score + phrase_bonus, 1.0)


def filter_relevant_citations(citations: list, question: str,
                               min_score: float = 0.08, max_sources: int = 4) -> list:
    """
    Keep only citations that are meaningfully relevant to the user's question.
    Returns an empty list when no citation clears the relevance threshold.
    """
    if not citations:
        return []

    scored = [
        (c, _score_citation(c, question))
        for c in citations
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    kept = []
    for c, score in scored:
        if score >= min_score and len(kept) < max_sources:
            kept.append(c)

    return kept


def query_knowledge_base(question: str, knowledge_base_id: str, model_arn: str,
                          mode: str = "rulebook", session_id: str = None,
                          region_name: str = None):
    """Query Bedrock Knowledge Base. Returns (response_text, citations, session_id)."""
    client = get_bedrock_client("bedrock-agent-runtime", region_name)
    if not client:
        return "Error: Could not initialise Bedrock client.", [], None

    if session_id is None:
        session_id = str(uuid.uuid4())

    if mode == "rulebook":
        prompt = f"""You are an expert NBA rules analyst with deep knowledge of basketball regulations.
Use only the retrieved rulebook sources provided by the knowledge base to answer the following question.

Question: {question}

Instructions:
1. Base the answer on retrieved sources and prior conversation context only when that context remains consistent with the sources.
2. If the retrieved material does not directly resolve the question, say that plainly and point to the closest relevant rule instead of guessing.
3. Separate direct support from any careful inference by using these headings exactly:
   Answer:
   Direct source support:
   Careful inference (if any):
4. For comparisons or scenarios, reason step by step from the cited rules and note any ambiguity that remains.
5. Cite specific rules and sections only when they are supported by the retrieved material.
6. Do not invent rule numbers, article numbers, penalties, dollar figures, or procedures.

Answer:"""
    else:
        prompt = f"""You are an expert on the NBA Collective Bargaining Agreement (CBA) and the NBA
Basketball Operations Manual. Use only the retrieved sources provided by the knowledge base to answer the following question.

Question: {question}

Instructions:
1. Base the answer on retrieved sources and prior conversation context only when that context remains consistent with the sources.
2. Explicitly note when information comes from the CBA versus the Operations Manual.
3. If the retrieved material does not directly resolve the question, say that plainly and point to the closest relevant article or section instead of guessing.
4. Use these headings exactly:
   Answer:
   Direct source support:
   Careful inference (if any):
5. Explain how multiple CBA articles or salary-cap rules interact when relevant, but distinguish direct support from inference.
6. Cite specific CBA articles or Operations Manual sections only when supported by the retrieved material.
7. Do not invent article numbers, salary figures, percentages, or procedural details.
8. Translate complex financial terms into plain language.

Answer:"""

    params = {
        "input": {"text": prompt},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": knowledge_base_id,
                "modelArn": model_arn,
            },
        },
    }
    if session_id:
        params["sessionId"] = session_id

    try:
        resp              = client.retrieve_and_generate(**params)
        new_session_id    = resp.get("sessionId", session_id)
        generated_text    = resp["output"]["text"]
        citations         = _extract_citations(resp)
        citations         = filter_relevant_citations(citations, question)
        return generated_text, citations, new_session_id

    except ClientError as e:
        code    = e.response["Error"]["Code"]
        message = e.response["Error"]["Message"]

        # Retry without session if session/config is stale
        if code == "ValidationException" and (
            "Knowledge base configurations cannot be modified" in message
            or "Session" in message
        ):
            params.pop("sessionId", None)
            try:
                resp           = client.retrieve_and_generate(**params)
                new_session_id = resp.get("sessionId")
                gen_text       = resp["output"]["text"]
                cits           = filter_relevant_citations(_extract_citations(resp), question)
                return gen_text, cits, new_session_id
            except Exception as retry_err:
                return f"Retry failed: {retry_err}", [], None

        return f"AWS Error ({code}): {message}", [], session_id

    except Exception as e:
        return f"Error querying knowledge base: {e}", [], session_id


# ─────────────────────────────────────────────
# QUIZ HELPERS
# ─────────────────────────────────────────────
QUIZ_TOPICS = {
    "rulebook": ["General Rules", "Fouls & Violations", "Shot Clock", "Out of Bounds", "Officials", "Overtime"],
    "cba":      ["Salary Cap", "Free Agency", "Trade Rules", "Contract Types", "Luxury Tax", "Waivers & Buyouts"],
}

# Sub-queries used to diversify retrieval per topic — each call picks one at random
_TOPIC_SUB_QUERIES = {
    # Rulebook
    "General Rules":      ["court dimensions and markings","jump ball and possession rules","number of players substitution rules","timing rules periods overtime","ball specifications and equipment"],
    "Fouls & Violations": ["personal foul definition and penalty","technical foul assessment rules","flagrant foul classification","loose ball foul away from play","clear path foul criteria"],
    "Shot Clock":         ["shot clock reset rules","shot clock violation penalty","shot clock off the rim rules","24 second clock operator duties","shot clock malfunction procedure"],
    "Out of Bounds":      ["ball out of bounds last touched","player out of bounds ruling","throw-in location after violation","baseline out of bounds after made basket","out of bounds on the sideline"],
    "Officials":          ["referee authority and jurisdiction","instant replay review triggers","official timeout procedures","correctable error rule","officials duties pregame"],
    "Overtime":           ["overtime period length","overtime jump ball or possession","overtime timeout allocation","scoring tied end of overtime","multiple overtime periods rules"],
    # CBA
    "Salary Cap":         ["salary cap calculation methodology","exceptions to salary cap","team salary definition","cap holds and cap room","cap year definition and timing"],
    "Free Agency":        ["unrestricted free agent eligibility","restricted free agent offer sheet","qualifying offer rules","early termination option","moratorium period free agency"],
    "Trade Rules":        ["trade deadline date","aggregation rules trade","trade kickers salary","sign and trade rules","cash in trades limits"],
    "Contract Types":     ["veteran minimum contract","two-way contract rules","exhibit 10 contract","two-way conversion rules","standard player contract provisions"],
    "Luxury Tax":         ["luxury tax threshold calculation","luxury tax repeater penalty","luxury tax distribution","apron rules hard cap","taxpayer mid-level exception"],
    "Waivers & Buyouts":  ["waiver claim priority order","stretch provision buyout","waiver wire process","buyout agreement timing","partial guarantee waiver"],
}

# Question-type rotator — forces Claude to ask different kinds of questions
_QUESTION_TYPES = [
    "a specific number, time limit, or threshold (e.g. 'how many seconds', 'what is the penalty amount')",
    "a scenario ruling (e.g. 'what happens when…', 'if a player does X then…')",
    "an exception or special case to the general rule",
    "the definition of a specific term used in the rules",
    "who is responsible for a specific action or call (player, official, team, etc.)",
    "the correct sequence or order of events in a specific situation",
]

import random as _random

def generate_quiz_question(mode: str, topic: str, kb_id: str, quiz_model_id: str,
                           region_name: str = None):
    """
    Generate a grounded, varied multiple-choice quiz question.
    - Randomises the retrieval sub-query so different source chunks are fetched each call.
    - Retrieves a larger pool (10 results) then randomly samples 4 to force variety.
    - Rotates question type so consecutive questions feel different.
    - Passes previously asked questions to Claude so it avoids repeating them.
    """
    rag_client     = get_bedrock_client("bedrock-agent-runtime", region_name)
    runtime_client = get_bedrock_runtime_client(region_name)
    if not rag_client or not runtime_client:
        return "Error: Could not initialise Bedrock clients.", [], None

    domain = "NBA official rulebook" if mode == "rulebook" else "NBA Collective Bargaining Agreement and salary cap rules"

    # ── Pick a random sub-query for this topic ───────────────────────────────
    sub_queries = _TOPIC_SUB_QUERIES.get(topic, [topic])
    retrieval_query = _random.choice(sub_queries)

    # ── Step 1: retrieve a larger pool then randomly sample ──────────────────
    try:
        retrieval_resp = rag_client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": retrieval_query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 10}},
        )
        all_chunks = []
        seen_chunks = set()
        for result in retrieval_resp.get("retrievalResults", []):
            chunk_text = result.get("content", {}).get("text", "").strip()
            if not chunk_text:
                continue
            fingerprint = chunk_text[:180]
            if fingerprint in seen_chunks:
                continue
            seen_chunks.add(fingerprint)

            metadata = result.get("metadata", {})
            location_parts = [
                f"{label.title()} {metadata[label]}"
                for label in ["rule", "section", "article", "part", "page"]
                if label in metadata
            ]
            if location_parts:
                all_chunks.append(f"[{' | '.join(location_parts)}]\n{chunk_text}")
            else:
                all_chunks.append(chunk_text)
    except Exception as e:
        return f"Quiz unavailable right now because source retrieval failed: {e}", [], None

    if len(all_chunks) < 2:
        return (
            "Quiz unavailable because the knowledge base did not return enough grounded source excerpts "
            f"for '{topic}'. Please try another topic or ask a direct question instead."
        ), [], None

    # Randomly sample up to 4 chunks so the source material varies each call
    sampled = _random.sample(all_chunks, min(4, len(all_chunks)))
    source_text = "\n\n---\n\n".join(sampled)

    # ── Pick a random question type ──────────────────────────────────────────
    q_type = _random.choice(_QUESTION_TYPES)

    # ── Build the "avoid repeating" block from session history ───────────────
    asked_so_far = get_quiz_history(mode, topic)
    avoid_block  = ""
    if asked_so_far:
        bullets = "\n".join(f"  - {q}" for q in asked_so_far[-8:])
        avoid_block = f"""
IMPORTANT — do NOT ask any of these questions that have already been asked:
{bullets}

Your question MUST cover a different specific rule, number, scenario, or term.
"""

    # ── Step 2: generate question grounded in retrieved text ─────────────────
    context_block = (
        f"Use ONLY the following source excerpts from the {domain}.\n"
        f"Do not use information outside these excerpts.\n\n"
        f"SOURCE EXCERPTS:\n{source_text}\n\n"
    )

    quiz_prompt = f"""{context_block}Generate one multiple-choice quiz question about: {topic}.

The question must be specifically about {q_type}.
{avoid_block}
Requirements:
- The correct answer MUST be directly supported by the source text above.
- The three wrong answers must be plausible but clearly incorrect per the sources.
- No trick questions or ambiguous wording.
- Focus on a concrete, specific fact — not a vague conceptual question.

Reply in EXACTLY this format (no extra text, no markdown, no preamble):
QUESTION: [question text]
A) [option]
B) [option]
C) [option]
D) [option]
ANSWER: [A, B, C, or D]
EXPLANATION: [one or two sentences citing the specific rule, article, or section that proves the answer]"""

    try:
        response = runtime_client.invoke_model(
            modelId=quiz_model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 700,
                "messages": [{"role": "user", "content": quiz_prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        text   = result.get("content", [{}])[0].get("text", "")

        # Store the question text in session history to avoid repeats
        parsed_check = text.split("QUESTION:")
        if len(parsed_check) > 1:
            q_text = parsed_check[1].split("\n")[0].strip()
            if q_text:
                asked_so_far.append(q_text)

        return text, [], None
    except Exception as e:
        return f"Error generating quiz: {e}", [], None


def parse_quiz(text: str):
    """Parse structured quiz text into a dict. Returns None on failure."""
    q = {"question": "", "options": {}, "answer": "", "explanation": ""}
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("QUESTION:"):
            q["question"] = line.removeprefix("QUESTION:").strip()
        elif len(line) >= 2 and line[0] in "ABCD" and line[1] == ")":
            q["options"][line[0]] = line[2:].strip()
        elif line.startswith("ANSWER:"):
            q["answer"] = line.removeprefix("ANSWER:").strip().upper()
        elif line.startswith("EXPLANATION:"):
            q["explanation"] = line.removeprefix("EXPLANATION:").strip()
    return q if q["question"] and q["options"] and q["answer"] else None


# ─────────────────────────────────────────────
# EXPORT HELPER
# ─────────────────────────────────────────────
def export_chat(messages: list, mode: str) -> str:
    t = THEMES[mode]
    lines = [
        f"# {t['title']}",
        f"**Mode:** {t['name']}  ",
        f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "", "---", "",
    ]
    for msg in messages:
        role  = "🧑 You" if msg["role"] == "user" else f"{t['icon']} Assistant"
        ts    = f" *{msg['timestamp']}*" if msg.get("timestamp") else ""
        lines += [f"### {role}{ts}", msg["content"], ""]

        if msg["role"] == "assistant" and msg.get("citations"):
            seen, srcs = set(), []
            for c in msg["citations"]:
                u = c.get("uri", "")
                if u not in seen:
                    seen.add(u)
                    srcs.append(f"- {u}")
            if srcs:
                lines += ["**Sources:**"] + srcs + [""]

        lines += ["---", ""]
    return "\n".join(lines)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    current_mode = st.session_state.mode
    current_messages = get_messages(current_mode)
    runtime_config = get_mode_runtime_config(current_mode)

    # ──────────────────────────────────────────
    # SIDEBAR
    # ──────────────────────────────────────────
    with st.sidebar:
        # Dark / Light toggle
        dark_label = "☀️ Light Mode" if st.session_state.dark_mode else "🌙 Dark Mode"
        if st.button(dark_label, use_container_width=True):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.rerun()

        st.markdown("---")

        # Mode toggle (sticky in sidebar)
        st.markdown("### 🔄 Mode")
        selected_mode = st.radio(
            "",
            options=["rulebook", "cba"],
            format_func=lambda x: THEMES[x]["name"],
            index=list(MODE_KEYS).index(current_mode),
            label_visibility="collapsed",
        )
        if selected_mode != current_mode:
            st.session_state.mode = selected_mode
            st.rerun()

        st.markdown("---")

        theme = THEMES[current_mode]
        kb_id = runtime_config["kb_id"]
        model_arn = runtime_config["model_arn"]
        quiz_model_id = runtime_config["quiz_model_id"]

        st.markdown("---")

        # Stats
        st.markdown("### 📊 Stats")
        q_count = len([m for m in current_messages if m["role"] == "user"])
        st.markdown(f"""
        <div class="metric-card">
            <h2 style="font-size:2rem;">{theme['icon']} {q_count}</h2>
            <p>Questions Asked</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Tips
        st.markdown("### 💡 Tips")
        if current_mode == "rulebook":
            st.markdown("""
- Ask about specific rules by number
- Ask follow-up questions (memory is on)
- Use **Scenario Simulator** for play rulings
- Try **Quiz Me** to test your knowledge
""")
        else:
            st.markdown("""
- Ask about CBA articles or salary-cap math
- Source badges show CBA vs Operations Manual
- Ask follow-up questions (memory is on)
- Try **Quiz Me** to test your CBA knowledge
""")

        st.markdown("---")

        # Actions
        st.markdown("### ⚡ Actions")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🗑️ Clear", use_container_width=True):
                clear_mode_state(current_mode)
                st.rerun()
        with c2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        # Export
        if current_messages:
            md_export = export_chat(current_messages, current_mode)
            ts_str    = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="📥 Export Chat",
                data=md_export,
                file_name=f"nba_{current_mode}_{ts_str}.md",
                mime="text/markdown",
                use_container_width=True,
            )

    # ──────────────────────────────────────────
    # HEADER
    # ──────────────────────────────────────────
    theme = THEMES[current_mode]
    st.markdown(f'<h1>{theme["title"]}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">{theme["subtitle"]}</p>', unsafe_allow_html=True)
    st.markdown("---")

    # ──────────────────────────────────────────
    # QUIZ ME
    # ──────────────────────────────────────────
    with st.expander("🎯 Quiz Me!", expanded=False):
        topics = QUIZ_TOPICS[current_mode]
        topic  = st.selectbox("Choose a topic:", topics, key="quiz_topic_select")

        if st.button("🎲 Generate Question", use_container_width=True, key="gen_quiz"):
            reset_quiz_state(current_mode)
            with st.spinner("Generating quiz question…"):
                raw_resp, _, _ = generate_quiz_question(
                    current_mode,
                    topic,
                    kb_id,
                    quiz_model_id,
                    runtime_config["region"],
                )
                parsed = parse_quiz(raw_resp)
                if parsed:
                    get_quiz_state(current_mode)["current"] = parsed
                else:
                    get_quiz_state(current_mode)["raw"] = raw_resp

        quiz_state = get_quiz_state(current_mode)
        quiz = quiz_state["current"]
        if quiz:
            st.markdown(f"**Q: {quiz['question']}**")
            user_ans = st.radio(
                "Your answer:",
                options=list(quiz["options"].keys()),
                format_func=lambda x: f"{x}) {quiz['options'][x]}",
                key=f"quiz_radio_{quiz['question'][:30]}",
            )
            if st.button("✅ Submit Answer", key="submit_quiz"):
                quiz_state["show_answer"] = True

            if quiz_state["show_answer"]:
                correct = quiz["answer"].strip().upper()
                if user_ans == correct:
                    st.success(f"🎉 Correct! The answer is **{correct}**.")
                else:
                    st.error(f"❌ Not quite. The correct answer is **{correct}**.")
                if quiz.get("explanation"):
                    st.info(f"📖 {quiz['explanation']}")

        elif quiz_state["raw"]:
            # Structured parse failed – show raw response
            if quiz_state["raw"].startswith("Quiz unavailable"):
                st.warning(quiz_state["raw"])
            elif quiz_state["raw"].startswith("Error generating quiz"):
                st.error(quiz_state["raw"])
            else:
                st.markdown(quiz_state["raw"])

    # ──────────────────────────────────────────
    # SCENARIO SIMULATOR (Rulebook only)
    # ──────────────────────────────────────────
    if current_mode == "rulebook":
        with st.expander("🏀 Scenario Simulator — Get a rules ruling", expanded=False):
            sc1, sc2 = st.columns(2)
            with sc1:
                play_type  = st.selectbox("Play type", [
                    "Drive to basket", "Three-point attempt", "Post play",
                    "Pick and roll", "Inbound play", "Jump ball", "Free throw", "Other",
                ], key="sim_play")
                game_clock = st.text_input("Game clock (e.g. 0:04)", key="sim_gclk")
            with sc2:
                shot_clock = st.selectbox("Shot clock", [
                    "Active (>0)", "Expired (0)", "Not applicable",
                ], key="sim_sclk")
                court_pos  = st.selectbox("Court position", [
                    "Paint/Key", "Mid-range", "Three-point line",
                    "Half court", "Backcourt", "Out-of-bounds area",
                ], key="sim_pos")

            situation = st.text_area(
                "Describe what happened:",
                placeholder="e.g. Player catches pass, takes two steps, pump-fakes, then shuffles again before releasing…",
                height=90,
                key="sim_desc",
            )

            if st.button("📋 Get Ruling", use_container_width=True, key="sim_submit") and situation.strip():
                scenario_prompt = (
                    f"Scenario Ruling Request:\n\n"
                    f"Play Type: {play_type}\n"
                    f"Court Position: {court_pos}\n"
                    f"Game Clock: {game_clock or 'Not specified'}\n"
                    f"Shot Clock: {shot_clock}\n\n"
                    f"Situation: {situation}\n\n"
                    f"Please provide a clear ruling on this situation, citing the exact rules that apply."
                )
                st.session_state.pending_prompts[current_mode] = scenario_prompt
                st.rerun()

    # ──────────────────────────────────────────
    # WELCOME SCREEN (no messages yet)
    # ──────────────────────────────────────────
    if len(current_messages) == 0:
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            st.markdown(f"""
            <div style="text-align:center;padding:2rem;">
                <h2 style="color:{theme['primary_color']};">{theme['icon']} Welcome!</h2>
                <p style="font-size:1.1rem;">
                    {"Ask me anything about NBA rules, regulations, and gameplay."
                     if current_mode == "rulebook"
                     else "Ask me about NBA contracts, salary cap, and league business rules."}
                </p>
            </div>""", unsafe_allow_html=True)

            st.markdown("### 🎯 Example Questions — click to ask:")
            ex1, ex2 = st.columns(2)
            for i, ex in enumerate(theme["examples"]):
                with (ex1 if i % 2 == 0 else ex2):
                    if st.button(f"{theme['icon']} {ex}", key=f"ex_{i}", use_container_width=True):
                        st.session_state.pending_prompts[current_mode] = ex
                        st.rerun()

            st.markdown("---")
            st.markdown("**💡 Tip:** Click an example above or type your question in the box below!")

    # ──────────────────────────────────────────
    # CHAT HISTORY
    # ──────────────────────────────────────────
    else:
        for msg in current_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"].replace("$", r"\$"))

                # Timestamp
                if msg.get("timestamp"):
                    st.markdown(f'<div class="msg-ts">🕐 {msg["timestamp"]}</div>', unsafe_allow_html=True)

                if msg["role"] == "assistant":
                    # Copy response
                    with st.expander("📋 Copy response"):
                        st.code(msg["content"], language=None)

                    # Citations
                    if msg.get("citations"):
                        st.markdown("---")
                        st.markdown("### 📚 Sources")
                        render_citations(msg["citations"], current_mode)

                    # Cross-mode suggestion (stored at render time)
                    if msg.get("cross_mode"):
                        other = msg["cross_mode"]
                        ot    = THEMES[other]
                        st.markdown(
                            f'<div class="cross-mode-box">💡 <strong>Did you know?</strong> '
                            f"This topic also has implications in <strong>{ot['name']}</strong>. "
                            f"Switch modes to explore further!</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(f"Switch to {ot['name']} →", key=f"sw_{msg.get('timestamp',id(msg))}"):
                            st.session_state.mode = other
                            st.rerun()

    # ──────────────────────────────────────────
    # CHAT INPUT
    # ──────────────────────────────────────────
    placeholder = (
        "Ask a question about NBA rules…"
        if current_mode == "rulebook"
        else "Ask about contracts, salary cap, or CBA rules…"
    )

    typed_prompt = st.chat_input(placeholder)

    # Resolve prompt (typed input wins; fallback to pending)
    prompt = typed_prompt
    pending_prompt = st.session_state.pending_prompts[current_mode]
    if not prompt and pending_prompt:
        prompt = pending_prompt
        st.session_state.pending_prompts[current_mode] = None

    if prompt:
        ts = datetime.now().strftime("%b %d, %I:%M %p")
        current_messages.append({"role": "user", "content": prompt, "timestamp": ts})

        with st.chat_message("user"):
            st.markdown(prompt.replace("$", r"\$"))
            st.markdown(f'<div class="msg-ts">🕐 {ts}</div>', unsafe_allow_html=True)

        # ── Animated loading card inside the assistant bubble ────────────────────
        loading_icon  = "🏀" if current_mode == "rulebook" else "💰"
        loading_label = (
            "Searching the NBA Rulebook…"
            if current_mode == "rulebook"
            else "Searching the CBA & Salary Cap docs…"
        )
        loading_html = f"""
<div class="loading-card">
    <div class="loading-ball">{loading_icon}</div>
    <div class="loading-ring"></div>
    <div class="loading-label">{loading_label}</div>
    <div class="loading-sub">Retrieving relevant sections and generating your answer</div>
    <div class="loading-dots" style="margin-top:0.8rem;">
        <span></span><span></span><span></span>
    </div>
</div>"""

        with st.chat_message("assistant"):
            loading_placeholder = st.empty()
            loading_placeholder.markdown(loading_html, unsafe_allow_html=True)

            cur_session = st.session_state.session_ids.get(current_mode)
            response, citations, new_session = query_knowledge_base(
                prompt,
                kb_id,
                model_arn,
                current_mode,
                session_id=cur_session,
                region_name=runtime_config["region"],
            )
            st.session_state.session_ids[current_mode] = new_session

            # Swap loading card for the actual response
            loading_placeholder.empty()

            resp_ts = datetime.now().strftime("%b %d, %I:%M %p")
            st.markdown(response.replace("$", r"\$"))
            st.markdown(f'<div class="msg-ts">🕐 {resp_ts}</div>', unsafe_allow_html=True)

            # Copy response
            with st.expander("📋 Copy response"):
                st.code(response, language=None)

            # Citations
            if citations:
                st.markdown("---")
                st.markdown("### 📚 Sources")
                render_citations(citations, current_mode)
            else:
                st.caption("No sufficiently relevant source excerpts were returned for this answer.")

            # Cross-mode detection & suggestion
            cross = detect_cross_mode(response, current_mode)
            if cross:
                ot = THEMES[cross]
                st.markdown(
                    f'<div class="cross-mode-box">💡 <strong>Did you know?</strong> '
                    f"This topic also has implications in <strong>{ot['name']}</strong>. "
                    f"Switch modes to explore further!</div>",
                    unsafe_allow_html=True,
                )
                if st.button(f"Switch to {ot['name']} →", key=f"switch_new_{resp_ts}"):
                    st.session_state.mode = cross
                    st.rerun()

        # Store assistant message
        current_messages.append({
            "role":       "assistant",
            "content":    response,
            "citations":  citations,
            "timestamp":  resp_ts,
            "cross_mode": cross,
        })


if __name__ == "__main__":
    main()
