import streamlit as st
import boto3
import json
import uuid
import re
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
def init_session_state():
    defaults = {
        "mode": "rulebook",
        "messages": [],
        "session_ids": {"rulebook": None, "cba": None},
        "dark_mode": False,
        "pending_prompt": None,
        "current_quiz": None,
        "quiz_raw": None,
        "show_quiz_answer": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

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
# AWS BEDROCK CLIENT
# ─────────────────────────────────────────────
@st.cache_resource
def get_bedrock_client():
    try:
        if "aws" in st.secrets:
            missing = [k for k in ["access_key_id", "secret_access_key"] if k not in st.secrets["aws"]]
            if missing:
                st.error(f"⚠️ Missing secret keys: {', '.join(missing)}")
                return None
            return boto3.client(
                service_name="bedrock-agent-runtime",
                aws_access_key_id=st.secrets["aws"]["access_key_id"],
                aws_secret_access_key=st.secrets["aws"]["secret_access_key"],
                region_name=st.secrets["aws"].get("region", "us-east-1"),
            )
        else:
            st.error("⚠️ No AWS credentials found in secrets!")
            return None
    except Exception as e:
        st.error(f"⚠️ Error initialising Bedrock client: {e}")
        return None


@st.cache_resource
def get_bedrock_runtime_client():
    """Direct model invocation client — used for quiz generation (no RAG needed)."""
    try:
        if "aws" in st.secrets:
            return boto3.client(
                service_name="bedrock-runtime",
                aws_access_key_id=st.secrets["aws"]["access_key_id"],
                aws_secret_access_key=st.secrets["aws"]["secret_access_key"],
                region_name=st.secrets["aws"].get("region", "us-east-1"),
            )
        return None
    except Exception as e:
        st.error(f"⚠️ Error initialising Bedrock runtime client: {e}")
        return None


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


def query_knowledge_base(question: str, knowledge_base_id: str, model_arn: str,
                          mode: str = "rulebook", session_id: str = None):
    """Query Bedrock Knowledge Base. Returns (response_text, citations, session_id)."""
    client = get_bedrock_client()
    if not client:
        return "Error: Could not initialise Bedrock client.", [], None

    if session_id is None:
        session_id = str(uuid.uuid4())

    if mode == "rulebook":
        prompt = f"""You are an expert NBA rules analyst with deep knowledge of basketball regulations.
Use the rulebook sources provided to answer the following question.

Question: {question}

Instructions:
1. ALWAYS synthesize an answer — even if no single rule directly addresses the question,
   combine definitions, examples, and related sections to construct a clear response.
   Never say the rulebook "does not directly address" something if related sections exist.
2. For questions comparing two concepts (e.g., fouls vs. violations), find the definitions
   and examples of each in the sources and explain the distinction clearly.
3. Combine multiple rules when needed — identify each relevant rule first, then explain
   how they connect.
4. For scenario / "what if" questions, reason step-by-step through the applicable rules.
5. Always cite specific rules (e.g., "According to Rule 12, Section II…").
6. Be confident in logical inferences — if the answer logically follows from the rules
   provided, state it as the answer.
7. Reference prior conversation context when answering follow-ups.

Answer:"""
    else:
        prompt = f"""You are an expert on the NBA Collective Bargaining Agreement (CBA) and the NBA
Basketball Operations Manual. Use the sources provided to answer the following question.

Question: {question}

Instructions:
1. Explicitly note when information comes from the CBA versus the Operations Manual.
2. Explain how multiple CBA articles or salary-cap rules interact when relevant.
3. Cite specific CBA articles or Operations Manual sections.
4. Translate complex financial terms into plain language.
5. Include relevant dollar figures or percentages where applicable.
6. Reference prior conversation context when answering follow-ups.

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
                return resp["output"]["text"], _extract_citations(resp), new_session_id
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

def generate_quiz_question(mode: str, topic: str, kb_id: str):
    """
    Generate a grounded multiple-choice quiz question.
    Step 1: retrieve relevant chunks from the KB for the topic.
    Step 2: pass those chunks to Claude directly so the question and answer
            are based on the actual source documents, not training-data guesses.
    """
    rag_client     = get_bedrock_client()
    runtime_client = get_bedrock_runtime_client()
    if not rag_client or not runtime_client:
        return "Error: Could not initialise Bedrock clients.", [], None

    domain = "NBA rulebook" if mode == "rulebook" else "NBA CBA / salary cap rules"

    # ── Step 1: retrieve relevant source chunks ──────────────────────────────
    try:
        retrieval_resp = rag_client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": topic},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
        )
        raw_chunks = retrieval_resp.get("retrievalResults", [])
        source_text = "\n\n---\n\n".join(
            r.get("content", {}).get("text", "") for r in raw_chunks if r.get("content", {}).get("text")
        )
    except Exception as e:
        source_text = ""  # Degrade gracefully — still try to generate

    # ── Step 2: generate question grounded in retrieved text ─────────────────
    if source_text:
        context_block = f"""Use ONLY the following source excerpts from the {domain} to write the question.
Do not use any information outside these excerpts.

SOURCE EXCERPTS:
{source_text}

"""
    else:
        context_block = f"Use your knowledge of the {domain} to write the question.\n\n"

    quiz_prompt = f"""{context_block}Generate one challenging but fair multiple-choice quiz question
specifically on the topic of: {topic}.

Rules:
- The correct answer MUST be directly supported by the source excerpts above.
- Wrong answers should be plausible but clearly incorrect based on the sources.
- Do not include trick questions or ambiguous wording.

Reply in EXACTLY this format (no extra text, no preamble, no markdown):
QUESTION: [question text]
A) [option]
B) [option]
C) [option]
D) [option]
ANSWER: [A, B, C, or D]
EXPLANATION: [one or two sentences quoting or paraphrasing the specific rule/article that proves the answer]"""

    try:
        response = runtime_client.invoke_model(
            modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 600,
                "messages": [{"role": "user", "content": quiz_prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        text = result.get("content", [{}])[0].get("text", "")
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
            index=list(THEMES.keys()).index(st.session_state.mode),
            label_visibility="collapsed",
        )
        if selected_mode != st.session_state.mode:
            st.session_state.mode     = selected_mode
            st.session_state.messages = []
            st.session_state.session_ids[selected_mode] = None
            st.session_state.current_quiz   = None
            st.session_state.quiz_raw       = None
            st.rerun()

        st.markdown("---")

        theme = THEMES[st.session_state.mode]

        # Hardcoded KB ID and model — derived from current mode
        kb_id     = theme["kb_id"]
        model_arn = (
            "us.anthropic.claude-opus-4-20250514-v1:0"
            if st.session_state.mode == "cba"
            else "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
        )

        st.markdown("---")

        # Stats
        st.markdown("### 📊 Stats")
        q_count = len([m for m in st.session_state.messages if m["role"] == "user"])
        st.markdown(f"""
        <div class="metric-card">
            <h2 style="font-size:2rem;">{theme['icon']} {q_count}</h2>
            <p>Questions Asked</p>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")

        # Tips
        st.markdown("### 💡 Tips")
        if st.session_state.mode == "rulebook":
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
                st.session_state.messages     = []
                st.session_state.current_quiz = None
                st.session_state.quiz_raw     = None
                st.session_state.session_ids[st.session_state.mode] = None
                st.rerun()
        with c2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        # Export
        if st.session_state.messages:
            md_export = export_chat(st.session_state.messages, st.session_state.mode)
            ts_str    = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="📥 Export Chat",
                data=md_export,
                file_name=f"nba_{st.session_state.mode}_{ts_str}.md",
                mime="text/markdown",
                use_container_width=True,
            )

    # ──────────────────────────────────────────
    # HEADER
    # ──────────────────────────────────────────
    theme = THEMES[st.session_state.mode]
    st.markdown(f'<h1>{theme["title"]}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">{theme["subtitle"]}</p>', unsafe_allow_html=True)
    st.markdown("---")

    # ──────────────────────────────────────────
    # QUIZ ME
    # ──────────────────────────────────────────
    with st.expander("🎯 Quiz Me!", expanded=False):
        topics = QUIZ_TOPICS[st.session_state.mode]
        topic  = st.selectbox("Choose a topic:", topics, key="quiz_topic_select")

        if st.button("🎲 Generate Question", use_container_width=True, key="gen_quiz"):
            st.session_state.current_quiz     = None
            st.session_state.quiz_raw         = None
            st.session_state.show_quiz_answer = False
            with st.spinner("Generating quiz question…"):
                raw_resp, _, _ = generate_quiz_question(st.session_state.mode, topic, kb_id)
                parsed = parse_quiz(raw_resp)
                if parsed:
                    st.session_state.current_quiz = parsed
                else:
                    st.session_state.quiz_raw = raw_resp

        quiz = st.session_state.current_quiz
        if quiz:
            st.markdown(f"**Q: {quiz['question']}**")
            user_ans = st.radio(
                "Your answer:",
                options=list(quiz["options"].keys()),
                format_func=lambda x: f"{x}) {quiz['options'][x]}",
                key=f"quiz_radio_{quiz['question'][:30]}",
            )
            if st.button("✅ Submit Answer", key="submit_quiz"):
                st.session_state.show_quiz_answer = True

            if st.session_state.show_quiz_answer:
                correct = quiz["answer"].strip().upper()
                if user_ans == correct:
                    st.success(f"🎉 Correct! The answer is **{correct}**.")
                else:
                    st.error(f"❌ Not quite. The correct answer is **{correct}**.")
                if quiz.get("explanation"):
                    st.info(f"📖 {quiz['explanation']}")

        elif st.session_state.quiz_raw:
            # Structured parse failed – show raw response
            st.markdown(st.session_state.quiz_raw)

    # ──────────────────────────────────────────
    # SCENARIO SIMULATOR (Rulebook only)
    # ──────────────────────────────────────────
    if st.session_state.mode == "rulebook":
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
                st.session_state.pending_prompt = scenario_prompt
                st.rerun()

    # ──────────────────────────────────────────
    # WELCOME SCREEN (no messages yet)
    # ──────────────────────────────────────────
    if len(st.session_state.messages) == 0:
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            st.markdown(f"""
            <div style="text-align:center;padding:2rem;">
                <h2 style="color:{theme['primary_color']};">{theme['icon']} Welcome!</h2>
                <p style="font-size:1.1rem;">
                    {"Ask me anything about NBA rules, regulations, and gameplay."
                     if st.session_state.mode == "rulebook"
                     else "Ask me about NBA contracts, salary cap, and league business rules."}
                </p>
            </div>""", unsafe_allow_html=True)

            st.markdown("### 🎯 Example Questions — click to ask:")
            ex1, ex2 = st.columns(2)
            for i, ex in enumerate(theme["examples"]):
                with (ex1 if i % 2 == 0 else ex2):
                    if st.button(f"{theme['icon']} {ex}", key=f"ex_{i}", use_container_width=True):
                        st.session_state.pending_prompt = ex
                        st.rerun()

            st.markdown("---")
            st.markdown("**💡 Tip:** Click an example above or type your question in the box below!")

    # ──────────────────────────────────────────
    # CHAT HISTORY
    # ──────────────────────────────────────────
    else:
        for msg in st.session_state.messages:
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
                        render_citations(msg["citations"], st.session_state.mode)

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
                            st.session_state.mode     = other
                            st.session_state.messages = []
                            st.session_state.session_ids[other] = None
                            st.rerun()

    # ──────────────────────────────────────────
    # CHAT INPUT
    # ──────────────────────────────────────────
    placeholder = (
        "Ask a question about NBA rules…"
        if st.session_state.mode == "rulebook"
        else "Ask about contracts, salary cap, or CBA rules…"
    )

    typed_prompt = st.chat_input(placeholder)

    # Resolve prompt (typed input wins; fallback to pending)
    prompt = typed_prompt
    if not prompt and st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if prompt:
        ts = datetime.now().strftime("%b %d, %I:%M %p")
        st.session_state.messages.append({"role": "user", "content": prompt, "timestamp": ts})

        with st.chat_message("user"):
            st.markdown(prompt.replace("$", r"\$"))
            st.markdown(f'<div class="msg-ts">🕐 {ts}</div>', unsafe_allow_html=True)

        # ── Visible status bar while the model runs ──────────────────────────────
        status_label = (
            "🏀 Searching the NBA Rulebook…"
            if st.session_state.mode == "rulebook"
            else "💰 Searching the CBA & Salary Cap docs…"
        )
        with st.status(status_label, expanded=True) as status:
            st.write("Retrieving relevant sections…")
            cur_session = st.session_state.session_ids.get(st.session_state.mode)
            response, citations, new_session = query_knowledge_base(
                prompt, kb_id, model_arn, st.session_state.mode, session_id=cur_session
            )
            st.session_state.session_ids[st.session_state.mode] = new_session
            src_count = len(citations)
            st.write(f"Generating answer from {src_count} source{'s' if src_count != 1 else ''}…")
            status.update(label="✅ Done!", state="complete", expanded=False)

        with st.chat_message("assistant"):
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
                render_citations(citations, st.session_state.mode)

            # Cross-mode detection & suggestion
            cross = detect_cross_mode(response, st.session_state.mode)
            if cross:
                ot = THEMES[cross]
                st.markdown(
                    f'<div class="cross-mode-box">💡 <strong>Did you know?</strong> '
                    f"This topic also has implications in <strong>{ot['name']}</strong>. "
                    f"Switch modes to explore further!</div>",
                    unsafe_allow_html=True,
                )
                if st.button(f"Switch to {ot['name']} →", key=f"switch_new_{resp_ts}"):
                    st.session_state.mode     = cross
                    st.session_state.messages = []
                    st.session_state.session_ids[cross] = None
                    st.rerun()

        # Store assistant message
        st.session_state.messages.append({
            "role":       "assistant",
            "content":    response,
            "citations":  citations,
            "timestamp":  resp_ts,
            "cross_mode": cross,
        })


if __name__ == "__main__":
    main()