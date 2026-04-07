import streamlit as st
import boto3
import json
import uuid
import re
import os
import html
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from botocore.exceptions import ClientError, ParamValidationError

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NBA Assistant - Rulebook & CBA",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
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
    "both": {
        "name": "🏀 + 💰 Crossbook Search",
        "kb_id": "",
        "primary_color": "#0D47A1",
        "secondary_color": "#F9A825",
        "gradient_start": "#0D47A1",
        "gradient_end": "#1976D2",
        "title": "🏀 + 💰 NBA Crossbook Workbench",
        "subtitle": "Compare gameplay rules with roster, contract, and operations consequences",
        "icon": "🏀 + 💰",
        "examples": [
            "How do technical foul suspensions connect to salary or contract consequences?",
            "What happens in both the rulebook and CBA when a player is waived while injured?",
            "Compare rulebook ejections with CBA fines or discipline language.",
            "What game-rule events can trigger salary-cap or roster implications?",
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
DUAL_MODE_SESSION_KEYS = ("both_rulebook", "both_cba")
DEFAULT_MODEL_ARNS = {
    "rulebook": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "cba": "us.anthropic.claude-opus-4-20250514-v1:0",
}
DEFAULT_QUIZ_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
RETRIEVAL_DEFAULTS = {
    "strict_grounding": True,
    "number_of_results": 5,
    "max_sources": 3,
    "exact_match_bias": False,
    "include_operations_manual": True,
}
RESPONSE_PROFILES = {
    "fast": {
        "label": "Fast",
        "description": "Lowest latency. May miss edge-case clauses.",
        "progressive_first_results": 3,
        "progressive_first_sources": 2,
        "allow_expanded_retry": False,
        "allow_manual_fallback": False,
        "enforce_strict_grounding": False,
    },
    "balanced": {
        "label": "Balanced",
        "description": "Best default mix of speed and grounded coverage.",
        "progressive_first_results": 3,
        "progressive_first_sources": 2,
        "allow_expanded_retry": True,
        "allow_manual_fallback": True,
        "enforce_strict_grounding": None,
    },
    "deep": {
        "label": "Deep Accuracy",
        "description": "Broader retrieval and stricter grounding.",
        "progressive_first_results": 4,
        "progressive_first_sources": 3,
        "allow_expanded_retry": True,
        "allow_manual_fallback": True,
        "enforce_strict_grounding": True,
    },
}
EXPORT_FORMATS = (
    "Transcript",
    "Scout note",
    "Cap memo",
    "Game ruling summary",
)
FOLLOWUP_ACTIONS = {
    "quote": "Exact clause",
    "fan": "Fan version",
    "analyst": "Analyst memo",
    "hypothetical": "Hypothetical",
    "bullets": "3 bullets",
}
QUICK_CHIPS = {
    "rulebook": [
        "Traveling",
        "Goaltending",
        "Clear path foul",
        "Instant replay",
        "Shot clock reset",
        "Out of bounds",
    ],
    "both": [
        "Technical foul suspension",
        "Waivers and roster spots",
        "Ejections and discipline",
        "Injuries and contracts",
        "Replay and fines",
        "Two-way availability",
    ],
    "cba": [
        "Restricted free agency",
        "Apron rules",
        "Waiver claims",
        "Two-way contracts",
        "Trade matching",
        "Luxury tax",
    ],
}
STARTER_PROMPTS = {
    "rulebook": {
        "What constitutes a traveling violation?": "What constitutes a traveling violation under the NBA rulebook? Define the rule, explain the common triggers and exceptions, and cite the exact rule language if available.",
        "How long is a shot clock in the NBA?": "How long is the NBA shot clock, and when does it reset to different amounts? Cite the rulebook language that governs the timing and reset rules.",
        "What are the rules for goaltending?": "What are the NBA rules for goaltending and basket interference? Explain when each is called and cite the relevant rule language.",
        "What's the difference between a foul and a violation?": "Under the NBA rulebook, what is a foul and what is a violation? Define each term, explain the practical difference, and cite the relevant rulebook definitions and examples.",
        "Traveling": "What constitutes a traveling violation under the NBA rulebook? Explain the core rule, common edge cases, and cite the exact rule language if available.",
        "Goaltending": "What is goaltending under the NBA rulebook? Explain when it is called, key exceptions, and cite the governing rule.",
        "Clear path foul": "What makes a foul a clear path foul in the NBA? Explain the criteria, penalty, and exact rule support.",
        "Instant replay": "How does instant replay work under the NBA rulebook? Explain the main review triggers, authority, and procedural limits with citations.",
        "Shot clock reset": "How do shot clock reset rules work in the NBA? Explain the common reset amounts and when each applies, with citations.",
        "Out of bounds": "How are out-of-bounds rulings handled in the NBA? Explain player/ball status and cite the relevant rule language.",
    },
    "both": {
        "Technical foul suspension": "Compare technical foul suspension consequences across the NBA rulebook and the CBA / Operations Manual. Explain the on-court rule, accumulation consequences, and any roster or pay implications.",
        "Waivers and roster spots": "Compare how waivers and roster spots are handled across gameplay rules, the CBA, and basketball operations materials. Explain where each source governs the issue.",
        "Ejections and discipline": "Compare ejections under the NBA rulebook with discipline, fines, or suspension treatment in the CBA / Operations materials.",
        "Injuries and contracts": "Compare how injuries are treated in gameplay administration versus contract / roster treatment under the CBA and Operations materials.",
        "Replay and fines": "Compare instant replay or review situations in the rulebook with any off-court consequences, discipline, or operations treatment in the CBA / Operations sources.",
        "Two-way availability": "Compare player availability questions under gameplay rules with two-way contract or roster eligibility rules under the CBA and Operations materials.",
    },
    "cba": {
        "Restricted free agency": "How does restricted free agency work under the NBA CBA? Explain qualifying offers, matching rights, offer sheets, timing, and cite the relevant clauses.",
        "Apron rules": "What are the first apron and second apron rules under the NBA CBA? Explain the key roster-building restrictions and cite the relevant clauses.",
        "Waiver claims": "How do waiver claim rules work under the NBA CBA and Basketball Operations materials? Explain claim priority, timing, and any salary or roster consequences.",
        "Two-way contracts": "How do two-way contracts work under the NBA CBA? Explain eligibility, service or game limits, conversion rules, and cite the relevant language.",
        "Trade matching": "How do NBA trade matching rules work under the CBA? Explain salary matching thresholds, over-the-cap trade rules, traded player exceptions, aggregation, and apron-related trade constraints with citations.",
        "Luxury tax": "How does the NBA luxury tax work under the CBA? Explain the threshold concept, repeater treatment, and practical team-building effects with citations.",
    },
}
RETRIEVAL_EXPANSIONS = {
    "rulebook": {
        "difference between a foul and a violation": "foul definition violation definition personal foul technical foul violation rule definitions distinction rule 10 rule 12",
        "foul and a violation": "foul definition violation definition distinction foul versus violation rule 10 rule 12",
        "traveling violation": "traveling pivot foot gather steps legal move rule 10",
        "goaltending": "goaltending basket interference scoring rule field goal touching ball on its downward flight",
        "shot clock": "24-second clock reset 14-second reset shot clock operator rule",
    },
    "cba": {
        "trade matching": "salary matching traded player exception over-the-cap incoming salary outgoing salary aggregation first apron second apron tax apron trade math",
        "waiver claims": "waiver claim priority claim order waiver period roster priority operations manual waived player claims",
        "two-way contracts": "two-way player eligibility conversion service days active list roster limit standard contract conversion",
        "apron rules": "first apron second apron team salary restrictions trade exception aggregation sign-and-trade taxpayer mid-level hard cap",
        "restricted free agency": "qualifying offer offer sheet matching rights moratorium restricted free agent",
        "luxury tax": "tax threshold repeater tax taxpayer non-taxpayer apron team salary",
    }
}
DOC_BROWSE_PRESETS = {
    "rulebook": ["Rule 4", "Rule 10", "Rule 11", "Rule 12", "Instant Replay", "Officials"],
    "both": ["Suspensions", "Waivers", "Discipline", "Roster limits", "Two-way rules", "Replay consequences"],
    "cba": ["Article II", "Article VI", "Article VII", "Waivers", "Luxury tax", "Two-way contracts"],
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
def _empty_quiz_state():
    return {
        "current": None,
        "raw": None,
        "show_answer": False,
    }


def _default_retrieval_settings():
    return dict(RETRIEVAL_DEFAULTS)


def init_session_state():
    defaults = {
        "mode": "cba",
        "dark_mode": False,
        "response_mode": "balanced",
        "session_ids": {
            **{mode: None for mode in MODE_KEYS},
            **{key: None for key in DUAL_MODE_SESSION_KEYS},
        },
        "export_format": EXPORT_FORMATS[0],
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
    for key in DUAL_MODE_SESSION_KEYS:
        st.session_state.session_ids.setdefault(key, None)

    if "pending_prompts" not in st.session_state:
        legacy_prompt = st.session_state.get("pending_prompt")
        st.session_state.pending_prompts = {
            mode: legacy_prompt if mode == current_mode else None
            for mode in MODE_KEYS
        }
    else:
        for mode in MODE_KEYS:
            st.session_state.pending_prompts.setdefault(mode, None)

    if "pending_prompt_meta" not in st.session_state:
        st.session_state.pending_prompt_meta = {mode: None for mode in MODE_KEYS}
    elif not isinstance(st.session_state.pending_prompt_meta, dict):
        legacy_meta = st.session_state.pending_prompt_meta
        st.session_state.pending_prompt_meta = {
            mode: legacy_meta if mode == current_mode else None
            for mode in MODE_KEYS
        }
    else:
        for mode in MODE_KEYS:
            st.session_state.pending_prompt_meta.setdefault(mode, None)

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

    if "retrieval_settings" not in st.session_state:
        st.session_state.retrieval_settings = {mode: _default_retrieval_settings() for mode in MODE_KEYS}
    else:
        for mode in MODE_KEYS:
            st.session_state.retrieval_settings.setdefault(mode, _default_retrieval_settings())

    if "bookmarks_by_mode" not in st.session_state:
        st.session_state.bookmarks_by_mode = {mode: [] for mode in MODE_KEYS}
    else:
        for mode in MODE_KEYS:
            st.session_state.bookmarks_by_mode.setdefault(mode, [])

    if "feedback_by_mode" not in st.session_state:
        st.session_state.feedback_by_mode = {mode: {} for mode in MODE_KEYS}
    else:
        for mode in MODE_KEYS:
            st.session_state.feedback_by_mode.setdefault(mode, {})

    if "response_cache_by_mode" not in st.session_state:
        st.session_state.response_cache_by_mode = {mode: {} for mode in MODE_KEYS}
        st.session_state.response_cache_by_mode["both"] = {}
    else:
        for mode in MODE_KEYS:
            st.session_state.response_cache_by_mode.setdefault(mode, {})
        st.session_state.response_cache_by_mode.setdefault("both", {})

    if "queued_action" not in st.session_state:
        st.session_state.queued_action = {mode: None for mode in MODE_KEYS}
    elif not isinstance(st.session_state.queued_action, dict):
        legacy_action = st.session_state.queued_action
        st.session_state.queued_action = {
            mode: legacy_action if mode == current_mode else None
            for mode in MODE_KEYS
        }
    else:
        for mode in MODE_KEYS:
            st.session_state.queued_action.setdefault(mode, None)


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


def get_retrieval_settings(mode: str = None):
    mode = mode or st.session_state.mode
    return st.session_state.retrieval_settings[mode]


def get_bookmarks(mode: str = None):
    mode = mode or st.session_state.mode
    return st.session_state.bookmarks_by_mode[mode]


def get_feedback_store(mode: str = None):
    mode = mode or st.session_state.mode
    return st.session_state.feedback_by_mode[mode]


def clear_mode_state(mode: str):
    st.session_state.messages_by_mode[mode] = []
    st.session_state.session_ids[mode] = None
    st.session_state.pending_prompts[mode] = None
    st.session_state.pending_prompt_meta[mode] = None
    st.session_state.queued_action[mode] = None
    st.session_state.quiz_asked[mode] = {}
    st.session_state.bookmarks_by_mode[mode] = []
    st.session_state.feedback_by_mode[mode] = {}
    st.session_state.response_cache_by_mode[mode] = {}
    reset_quiz_state(mode)
    if mode == "both":
        for key in DUAL_MODE_SESSION_KEYS:
            st.session_state.session_ids[key] = None
        st.session_state.response_cache_by_mode["both"] = {}


def make_message_id() -> str:
    return uuid.uuid4().hex[:12]


def get_message_id(msg: dict) -> str:
    return msg.get("id") or f"legacy-{msg.get('timestamp', 'no-ts')}-{abs(hash(msg.get('content', '')))}"


def queue_prompt(
    mode: str,
    prompt: str,
    action_key: str = None,
    origin: str = "generic",
    label: str = None,
    retrieval_overrides: dict = None,
):
    st.session_state.pending_prompts[mode] = prompt
    st.session_state.pending_prompt_meta[mode] = {
        "origin": origin,
        "label": label or prompt[:88],
        "retrieval_overrides": retrieval_overrides or {},
    }
    st.session_state.queued_action[mode] = action_key


def response_profile() -> dict:
    selected = st.session_state.get("response_mode", "balanced")
    return RESPONSE_PROFILES.get(selected, RESPONSE_PROFILES["balanced"])


def with_response_profile(base_settings: dict, response_mode: str, retrieval_overrides: dict = None) -> dict:
    profile = RESPONSE_PROFILES.get(response_mode, RESPONSE_PROFILES["balanced"])
    effective = dict(base_settings)

    if response_mode == "fast":
        effective["number_of_results"] = min(effective.get("number_of_results", 5), 4)
        effective["max_sources"] = min(effective.get("max_sources", 3), 3)
    elif response_mode == "deep":
        effective["number_of_results"] = min(effective.get("number_of_results", 5) + 2, 10)
        effective["max_sources"] = min(effective.get("max_sources", 3) + 1, 6)
        effective["exact_match_bias"] = True

    strict_override = profile.get("enforce_strict_grounding")
    if strict_override is not None:
        effective["strict_grounding"] = strict_override

    if retrieval_overrides:
        effective.update(retrieval_overrides)
    return effective


def progressive_first_pass_settings(settings: dict, response_mode: str) -> dict:
    profile = RESPONSE_PROFILES.get(response_mode, RESPONSE_PROFILES["balanced"])
    first_pass = dict(settings)
    first_pass["number_of_results"] = min(
        settings.get("number_of_results", 5),
        profile.get("progressive_first_results", 3),
    )
    first_pass["max_sources"] = min(
        settings.get("max_sources", 3),
        profile.get("progressive_first_sources", 2),
    )
    return first_pass


def _cache_store(mode: str) -> dict:
    return st.session_state.response_cache_by_mode.setdefault(mode, {})


def _cache_key(question: str, mode: str, response_mode: str, retrieval_settings: dict, session_scope: str) -> str:
    payload = {
        "mode": mode,
        "response_mode": response_mode,
        "question": question.strip().lower(),
        "results": retrieval_settings.get("number_of_results"),
        "sources": retrieval_settings.get("max_sources"),
        "strict": retrieval_settings.get("strict_grounding"),
        "exact": retrieval_settings.get("exact_match_bias"),
        "ops": retrieval_settings.get("include_operations_manual"),
        "session_scope": session_scope,
    }
    serial = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serial.encode("utf-8")).hexdigest()


def _cache_get(mode: str, cache_key: str):
    entry = _cache_store(mode).get(cache_key)
    if not entry:
        return None
    return entry.get("response"), entry.get("citations", [])


def _cache_set(mode: str, cache_key: str, response: str, citations: list):
    if not response or response.lower().startswith("error querying knowledge base"):
        return
    store = _cache_store(mode)
    store[cache_key] = {
        "response": response,
        "citations": citations,
        "created_at": time.time(),
    }
    if len(store) > 120:
        oldest_key = min(store.keys(), key=lambda key: store[key].get("created_at", 0))
        store.pop(oldest_key, None)


def save_bookmark(mode: str, msg: dict):
    bookmarks = get_bookmarks(mode)
    bookmark_id = get_message_id(msg)
    if any(b["id"] == bookmark_id for b in bookmarks):
        return

    title_source = msg.get("question") or msg.get("content", "")
    bookmarks.append({
        "id": bookmark_id,
        "title": title_source[:72] + ("..." if len(title_source) > 72 else ""),
        "question": msg.get("question", ""),
        "content": msg.get("content", ""),
        "timestamp": msg.get("timestamp", ""),
        "mode": mode,
    })


def record_feedback(mode: str, message_id: str, label: str):
    get_feedback_store(mode)[message_id] = {
        "label": label,
        "timestamp": datetime.now().strftime("%b %d, %I:%M %p"),
    }


def parse_answer_sections(text: str) -> dict:
    sections = {}
    current = "Answer"
    sections[current] = []
    heading_map = {
        "answer": "Answer",
        "direct source support": "Direct source support",
        "careful inference (if any)": "Careful inference",
        "careful inference": "Careful inference",
        "related rule/cba topic": "Related topic",
        "rulebook view": "Rulebook view",
        "cba / operations view": "CBA / Operations view",
        "cba/operations view": "CBA / Operations view",
        "takeaway": "Takeaway",
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            sections.setdefault(current, []).append("")
            continue
        normalized = line.rstrip(":").lower()
        if normalized in heading_map:
            current = heading_map[normalized]
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(raw_line)

    return {
        title: "\n".join(lines).strip()
        for title, lines in sections.items()
        if "\n".join(lines).strip()
    } or {"Answer": text.strip()}


def _sentence_like_chunks(text: str) -> list:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    chunks = []
    for part in re.split(r"(?<=[.!?])\s+", normalized):
        for clause in re.split(r";\s+", part):
            cleaned = clause.strip(" -*•\t")
            if cleaned:
                chunks.append(cleaned)
    return chunks


def is_three_bullet_response(text: str) -> bool:
    non_empty = [line.strip() for line in text.splitlines() if line.strip()]
    bullets = [line for line in non_empty if re.match(r"^[-*•]\s+", line)]
    return len(non_empty) == 3 and len(bullets) == 3


def enforce_three_bullet_response(text: str, citations: list, mode: str) -> str:
    if is_three_bullet_response(text):
        return text

    sections = parse_answer_sections(text)
    candidate_chunks = []
    for section_name in ("Answer", "Direct source support", "Careful inference"):
        section_text = sections.get(section_name, "")
        candidate_chunks.extend(_sentence_like_chunks(section_text))
    if not candidate_chunks:
        candidate_chunks = _sentence_like_chunks(text)

    bullets = []
    seen = set()
    for chunk in candidate_chunks:
        normalized = chunk.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        bullets.append(chunk.rstrip(".") + ".")
        if len(bullets) == 3:
            break

    if not bullets:
        fallback = text.strip()
        return f"- {fallback}" if fallback else text

    while len(bullets) < 3:
        bullets.append(bullets[-1])

    source_labels = [citation_title(citation, mode) for citation in dedupe_citations(citations)[:3]]
    if not source_labels:
        source_labels = ["grounded sources attached"]

    formatted = []
    for idx, bullet in enumerate(bullets[:3]):
        label = source_labels[min(idx, len(source_labels) - 1)]
        formatted.append(f"- {bullet} ({label})")
    return "\n".join(formatted)


def build_followup_prompt(action_key: str, msg: dict, mode: str) -> str:
    question = msg.get("question") or "the previous question"
    source_hint = "Use the same source type and keep citations grounded."
    prompts = {
        "quote": (
            f"Using the same topic as this earlier question: '{question}', give me the exact clause or closest verbatim source language only. "
            f"Keep the answer quote-focused and concise. {source_hint}"
        ),
        "fan": (
            f"Rewrite your answer to this question for a casual NBA fan: '{question}'. "
            f"Use plain language, short sentences, and keep the citations grounded. {source_hint}"
        ),
        "analyst": (
            f"Rewrite your answer to this question as a front-office analyst memo: '{question}'. "
            f"Lead with the key takeaway, then implications, then direct source support. {source_hint}"
        ),
        "hypothetical": (
            f"For the earlier question '{question}', give me one realistic hypothetical example and walk through how the rule or CBA language applies. "
            f"Label assumptions clearly. {source_hint}"
        ),
        "bullets": (
            f"Summarize your answer to '{question}' in exactly 3 markdown bullet points with grounded citations. "
            f"Return only the three bullets and nothing else. Each bullet must be a single concise sentence. {source_hint}"
        ),
    }
    return prompts[action_key]


def build_compare_prompt(left: str, right: str, mode: str) -> str:
    scope = (
        "Use both the NBA Rulebook and CBA / Operations Manual sources."
        if mode == "both"
        else f"Use the {THEMES[mode]['name']} sources."
    )
    return (
        f"Compare these two items: '{left}' and '{right}'. {scope} "
        "Answer with sections titled: Answer, Direct source support, Careful inference (if any), and Key differences."
    )


def build_crossbook_prompt(topic: str) -> str:
    return (
        f"For the topic '{topic}', compare the gameplay-rule view with the CBA / Basketball Operations view. "
        "Explain what the rulebook governs, what the CBA or Operations Manual governs, and where the two interact."
    )


def build_doc_browse_prompt(browse_type: str, browse_value: str, mode: str) -> str:
    scope = (
        "Search across both the Rulebook and CBA / Operations sources."
        if mode == "both"
        else f"Search within the {THEMES[mode]['name']} sources."
    )
    return (
        f"Browse by {browse_type.lower()}: '{browse_value}'. {scope} "
        "Show the most relevant clause, explain it briefly, and list adjacent related sections if available."
    )


def suggest_reformulations(question: str, mode: str) -> list:
    narrowed = question.rstrip(" ?.")
    if mode == "rulebook":
        return [
            f"What exact rule or section addresses {narrowed.lower()}?",
            f"Give me the verbatim rule language for {narrowed.lower()}.",
            f"Walk through a game scenario involving {narrowed.lower()} step by step.",
        ]
    if mode == "cba":
        return [
            f"What exact CBA article or operations section covers {narrowed.lower()}?",
            f"Explain {narrowed.lower()} in plain language with the exact clause.",
            f"What are the practical roster or salary-cap implications of {narrowed.lower()}?",
        ]
    return [
        f"Compare the rulebook impact and CBA impact of {narrowed.lower()}.",
        f"Show me the exact clauses in both sources for {narrowed.lower()}.",
        f"What happens on-court and off-court when {narrowed.lower()}?",
    ]


def needs_reformulation(response: str, citations: list) -> bool:
    unresolved_markers = (
        "does not directly resolve",
        "closest relevant",
        "not enough grounded",
        "no sufficiently relevant",
        "error querying knowledge base",
        "aws error",
        "unable to assist",
    )
    return (not citations) or any(marker in response.lower() for marker in unresolved_markers)


def starter_prompt_for(mode: str, label: str) -> str:
    mapped = STARTER_PROMPTS.get(mode, {}).get(label)
    if mapped:
        return mapped
    if mode == "cba":
        return f"{label} Explain it in plain language, cite the exact CBA or Operations provisions, and include the key practical implications."
    if mode == "both":
        return build_crossbook_prompt(label)
    return f"{label} Explain the rule clearly and cite the exact rule language if available."


def loading_state_for(mode: str) -> dict:
    if mode == "rulebook":
        return {
            "icon": "🏀",
            "label": "Searching the NBA Rulebook…",
            "sub": "Locating the governing rule, checking definitions and exceptions, and preparing a clear ruling.",
            "steps": ["Finding the right rule", "Checking exceptions", "Drafting the ruling"],
            "min_display_seconds": 0.0,
        }
    if mode == "both":
        return {
            "icon": "🏀 + 💰",
            "label": "Searching both the Rulebook and CBA lanes…",
            "sub": "Cross-checking gameplay rules against roster, contract, and operations language.",
            "steps": ["Pulling Rulebook sources", "Pulling CBA sources", "Stitching both views together"],
            "min_display_seconds": 0.0,
        }
    return {
        "icon": "💰",
        "label": "Searching the CBA & Salary Cap docs…",
        "sub": "Large CBA lookups can take a bit longer while the app matches clauses and trade / cap terminology.",
        "steps": ["Finding the clause", "Checking cap mechanics", "Writing the takeaway"],
        "min_display_seconds": 0.0,
    }


def build_status_timeline_html(active_stage: str, detail: str = "") -> str:
    stages = [
        ("retrieving", "Retrieving"),
        ("ranking", "Ranking"),
        ("drafting", "Drafting"),
        ("finalizing", "Finalizing"),
    ]
    stage_order = {key: idx for idx, (key, _) in enumerate(stages)}
    active_idx = stage_order.get(active_stage, 0)
    pills = []
    for idx, (key, label) in enumerate(stages):
        cls = "status-step"
        if idx < active_idx:
            cls += " status-done"
        elif idx == active_idx:
            cls += " status-active"
        pills.append(f'<span class="{cls}">{label}</span>')
    detail_html = f'<div class="status-detail">{html.escape(detail)}</div>' if detail else ""
    return (
        '<div class="status-timeline">'
        f'{"".join(pills)}'
        f"{detail_html}"
        "</div>"
    )


def expand_query_for_retrieval(question: str, mode: str) -> str:
    expansions = RETRIEVAL_EXPANSIONS.get(mode, {})
    question_lower = question.lower()
    matched = [hint for phrase, hint in expansions.items() if phrase in question_lower]
    if not matched:
        return question
    return f"{question}\n\nRetrieval hints: {'; '.join(matched)}."


def safe_markdown(text: str) -> str:
    return text.replace("$", r"\$")


def html_safe(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")

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
.hero-shell {{
    background:
        radial-gradient(circle at top right, {p}33 0%, transparent 35%),
        linear-gradient(135deg, {surface} 0%, {chat_bg} 100%);
    border: 1px solid {p}33;
    border-radius: 20px;
    padding: 1.4rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 10px 30px rgba(0,0,0,0.08);
}}
.hero-kicker {{
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    background: {p}22;
    color: {p} !important;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.4px;
    margin-bottom: 0.6rem;
}}
.hero-title {{
    font-size: 2rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 0;
}}
.hero-sub {{
    margin-top: 0.55rem;
    font-size: 1rem;
    color: {text} !important;
    opacity: 0.88;
}}

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
.relevance-note {{
    font-size: 0.8rem;
    color: #7f8c8d !important;
    margin-top: -0.15rem;
    margin-bottom: 0.55rem;
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
.source-rail {{
    background: {surface};
    border: 1px solid {p}22;
    border-radius: 16px;
    padding: 1rem;
    box-shadow: 0 8px 20px rgba(0,0,0,0.06);
}}
.answer-card {{
    background: {surface};
    border: 1px solid {p}22;
    border-radius: 16px;
    padding: 1rem 1.1rem;
    box-shadow: 0 8px 20px rgba(0,0,0,0.05);
}}
.answer-section {{
    background: {chat_bg};
    border-radius: 14px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.9rem;
    border-left: 4px solid {p};
}}
.section-label {{
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: {p} !important;
    font-weight: 800;
    margin-bottom: 0.35rem;
}}
.helper-card {{
    background: linear-gradient(135deg, {p}15 0%, {s}12 100%);
    border: 1px solid {p}22;
    border-radius: 14px;
    padding: 0.85rem 1rem;
    margin: 0.6rem 0;
}}
.quote-card {{
    background: {chat_bg};
    border-radius: 14px;
    padding: 0.95rem 1rem;
    border-left: 4px solid {s};
    margin-bottom: 0.75rem;
    font-style: italic;
}}
.split-subhead {{
    font-size: 0.86rem;
    color: {sub_text} !important;
    margin-bottom: 0.5rem;
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
.bookmark-card {{
    background: {surface};
    border: 1px solid {p}22;
    border-radius: 12px;
    padding: 0.8rem 0.9rem;
    margin-bottom: 0.6rem;
}}
.bookmark-meta {{
    color: #888 !important;
    font-size: 0.78rem;
}}
.feedback-pill {{
    display: inline-block;
    border-radius: 999px;
    padding: 0.22rem 0.65rem;
    font-size: 0.76rem;
    font-weight: 700;
    background: {p}18;
    color: {p} !important;
    margin-top: 0.5rem;
}}

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
.chip-intro {{
    font-size: 0.83rem;
    color: #7f8c8d !important;
    margin-bottom: 0.5rem;
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
.loading-steps {{
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.45rem;
    margin-top: 0.9rem;
}}
.loading-step {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    border-radius: 999px;
    padding: 0.28rem 0.65rem;
    font-size: 0.74rem;
    font-weight: 700;
    color: {p} !important;
    -webkit-text-fill-color: {p} !important;
    border: 1px solid {p}33;
    background: {p}12;
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
.thinking-banner {{
    position: sticky;
    top: 0.5rem;
    z-index: 20;
    padding: 0.9rem 1rem;
    margin: 0.35rem 0 1rem 0;
    border-radius: 14px;
    border: 1px solid {p}44;
    background: linear-gradient(135deg, {surface} 0%, {chat_bg} 100%);
    box-shadow: 0 8px 22px rgba(0,0,0,0.08);
}}
.thinking-title {{
    color: {p} !important;
    font-weight: 800;
    margin-bottom: 0.25rem;
}}
.thinking-sub {{
    font-size: 0.86rem;
    color: {text} !important;
    opacity: 0.82;
    margin-bottom: 0.45rem;
}}
.thinking-steps {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-bottom: 0.55rem;
}}
.thinking-step {{
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 0.26rem 0.6rem;
    font-size: 0.74rem;
    font-weight: 700;
    color: {p} !important;
    -webkit-text-fill-color: {p} !important;
    border: 1px solid {p}33;
    background: {p}12;
}}
.thinking-track {{
    width: 100%;
    height: 8px;
    border-radius: 999px;
    background: {p}22;
    overflow: hidden;
}}
.thinking-track::after {{
    content: "";
    display: block;
    width: 35%;
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, transparent 0%, {p} 35%, {theme["gradient_end"]} 100%);
    animation: thinking-slide 1.25s ease-in-out infinite;
}}
@keyframes thinking-slide {{
    0% {{ transform: translateX(-120%); }}
    100% {{ transform: translateX(320%); }}
}}

/* ── Stray Streamlit chrome ────────────── */
footer {{ display: none !important; }}

/* ── Floating Mobile Nav ───────────────── */
.mobile-nav {{
    position: fixed;
    left: 50%;
    bottom: 14px;
    transform: translateX(-50%);
    z-index: 999;
    display: flex;
    gap: 0.55rem;
    padding: 0.5rem 0.7rem;
    border-radius: 999px;
    backdrop-filter: blur(12px);
    background: rgba(15, 52, 96, 0.82);
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
}}
.mobile-nav a {{
    color: white !important;
    text-decoration: none !important;
    font-size: 0.8rem;
    font-weight: 700;
    padding: 0.15rem 0.35rem;
}}

/* ── Responsive ────────────────────────── */
@media (max-width: 768px) {{
    .main {{ padding: 1rem !important; padding-bottom: 100px !important; }}
    h1    {{ font-size: 1.4rem !important; }}
    .hero-title {{ font-size: 1.5rem; }}
    .hero-shell {{ padding: 1rem; }}
}}
@media (min-width: 769px) {{
    .mobile-nav {{ display: none; }}
}}
</style>
"""


def build_visual_overrides(theme: dict, dark: bool) -> str:
    p = theme["primary_color"]
    s = theme["secondary_color"]
    if dark:
        paper = "#0C1422"
        panel = "#121C2D"
        panel_alt = "#18263A"
        text = "#E8EEF7"
        muted = "#96A6BE"
        grid = "rgba(255,255,255,0.08)"
        border = "rgba(190,204,227,0.18)"
    else:
        paper = "#F3F1EC"
        panel = "#FBFAF6"
        panel_alt = "#F7F3EC"
        text = "#1F2933"
        muted = "#5E6978"
        grid = "rgba(31,41,51,0.11)"
        border = "rgba(31,41,51,0.16)"

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=IBM+Plex+Mono:wght@400;500;600&family=Source+Sans+3:wght@400;500;600;700&display=swap');

:root {{
    --paper: {paper};
    --panel: {panel};
    --panel-alt: {panel_alt};
    --ink: {text};
    --muted: {muted};
    --grid: {grid};
    --accent: {p};
    --accent-alt: {s};
    --line: {border};
}}

.stApp {{
    background:
        radial-gradient(1400px 680px at -15% -18%, {p}26 0%, transparent 52%),
        radial-gradient(1100px 560px at 102% -10%, {s}22 0%, transparent 56%),
        radial-gradient(860px 460px at 18% 100%, {p}14 0%, transparent 56%),
        linear-gradient(180deg, {paper} 0%, {panel_alt} 100%),
        var(--paper) !important;
}}
.main {{
    background: transparent !important;
}}

html, body, .stApp, .stMarkdown, .stButton button, .stTextInput, .stSelectbox, .stChatInput {{
    font-family: "Source Sans 3", "Segoe UI", sans-serif !important;
}}
h1, h2, h3, .hero-title, .section-label {{
    font-family: "Libre Baskerville", Georgia, serif !important;
}}
code, pre, .stCodeBlock, .stJson {{
    font-family: "IBM Plex Mono", ui-monospace, monospace !important;
}}

p, span, li, label, .stMarkdown p, .stMarkdown li {{
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}}

.hero-shell {{
    position: relative;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 22px;
    background:
        linear-gradient(145deg, var(--panel) 0%, var(--panel-alt) 100%);
    box-shadow: 0 22px 40px rgba(0,0,0,0.10);
}}
.hero-shell::after {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(125deg, transparent 0%, transparent 64%, {p}10 100%);
    pointer-events: none;
}}
.hero-kicker {{
    border: 1px solid {p}55;
    background: {p}18;
    backdrop-filter: blur(6px);
}}
.hero-title {{
    letter-spacing: -0.02em;
}}
.hero-sub {{
    color: var(--muted) !important;
    font-size: 1.02rem;
}}

.answer-card, .source-rail, .helper-card, .bookmark-card, .metric-card {{
    border: 1px solid var(--line) !important;
    background: linear-gradient(160deg, var(--panel) 0%, var(--panel-alt) 100%) !important;
    box-shadow: 0 16px 30px rgba(0,0,0,0.08);
}}
.answer-section {{
    border-left: 4px solid var(--accent);
    background: linear-gradient(120deg, {p}10 0%, transparent 70%);
}}
.section-label {{
    color: var(--accent) !important;
    letter-spacing: 0.7px;
}}
.source-excerpt, .quote-card {{
    border: 1px solid var(--line);
}}
.relevance-note, .msg-ts, .split-subhead, .bookmark-meta {{
    color: var(--muted) !important;
    -webkit-text-fill-color: var(--muted) !important;
}}

div[data-testid="stButton"] button {{
    border-radius: 999px !important;
    border: 1px solid var(--line) !important;
    background: linear-gradient(180deg, var(--panel) 0%, var(--panel-alt) 100%) !important;
    color: var(--ink) !important;
    transition: transform 0.14s ease, box-shadow 0.14s ease, border-color 0.14s ease;
}}
div[data-testid="stButton"] button:hover {{
    border-color: {p}66 !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 22px rgba(0,0,0,0.15);
}}
div[data-testid="stButton"] button:focus {{
    outline: none !important;
    box-shadow: 0 0 0 3px {p}33 !important;
}}

div[data-testid="stChatInput"] {{
    background: var(--paper) !important;
    border: 1.5px solid {p}88 !important;
    border-radius: 18px !important;
    box-shadow: 0 8px 20px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.14) !important;
}}
div[data-testid="stChatInput"]:focus-within {{
    border-color: {p} !important;
    box-shadow: 0 0 0 2px {p}2F, 0 10px 22px var(--shadow) !important;
}}
div[data-testid="stChatInput"] > div {{
    background: var(--paper) !important;
    border-radius: 18px !important;
    border: 1px solid {p}40 !important;
}}
.stChatFloatingInputContainer,
[data-testid="stChatInputContainer"],
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div,
[data-testid="stBottom"] {{
    background: var(--paper) !important;
    box-shadow: none !important;
    border: none !important;
}}
.stChatInputContainer {{
    background: var(--paper) !important;
    border: none !important;
}}
div[data-testid="stChatInput"] textarea,
.stChatInputContainer textarea,
[data-baseweb="textarea"] textarea {{
    background: var(--paper) !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}}
div[data-testid="stChatInput"] textarea::placeholder,
.stChatInputContainer textarea::placeholder {{
    color: var(--muted) !important;
    -webkit-text-fill-color: var(--muted) !important;
}}

.chip-intro {{
    letter-spacing: 0.3px;
    color: var(--muted) !important;
}}
[data-testid="stSidebar"] {{
    display: none !important;
}}
[data-testid="collapsedControl"] {{
    display: none !important;
}}

.top-rail {{
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 0.9rem 1rem;
    margin-bottom: 1rem;
    background: linear-gradient(145deg, var(--panel) 0%, var(--panel-alt) 100%);
    box-shadow: 0 12px 24px rgba(0,0,0,0.07);
}}
.top-rail-title {{
    font-family: "IBM Plex Mono", monospace;
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.55px;
    color: var(--muted) !important;
    margin-bottom: 0.55rem;
}}
.top-rail-note {{
    font-size: 0.86rem;
    color: var(--muted) !important;
}}
.control-drawer {{
    border: 1px solid var(--line);
    border-radius: 16px;
    background: linear-gradient(145deg, var(--panel) 0%, var(--panel-alt) 100%);
    padding: 0.9rem 1rem;
}}
.mode-chip {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.28rem 0.7rem;
    border-radius: 999px;
    border: 1px solid {p}55;
    background: {p}15;
    color: var(--ink) !important;
    font-size: 0.79rem;
    font-weight: 700;
}}

.sidebar-metrics {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
    margin-bottom: 0.45rem;
}}
.sidebar-metric {{
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 0.55rem 0.65rem;
    background: linear-gradient(155deg, var(--panel) 0%, var(--panel-alt) 100%);
}}
.sidebar-metric-label {{
    display: block;
    font-size: 0.72rem;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: var(--muted) !important;
}}
.sidebar-metric-value {{
    display: block;
    font-family: "Libre Baskerville", Georgia, serif;
    font-size: 1.1rem;
    color: var(--ink) !important;
    line-height: 1.2;
}}

.signal-strip {{
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 1.05rem 1.1rem;
    margin-bottom: 1rem;
    background:
        linear-gradient(145deg, var(--panel) 0%, var(--panel-alt) 100%);
    box-shadow: 0 14px 28px rgba(0,0,0,0.08);
}}
.signal-title {{
    font-family: "Libre Baskerville", Georgia, serif;
    font-size: 1.1rem;
    color: var(--ink) !important;
    margin-bottom: 0.15rem;
}}
.signal-sub {{
    color: var(--muted) !important;
    font-size: 0.88rem;
    margin-bottom: 0.75rem;
}}
.signal-grid {{
    display: grid;
    grid-template-columns: minmax(170px, 230px) 1fr;
    gap: 0.9rem;
    align-items: stretch;
}}
.signal-kpis {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.45rem;
}}
.signal-kpi {{
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 0.45rem 0.55rem;
    background: {p}10;
}}
.signal-kpi-label {{
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--muted) !important;
}}
.signal-kpi-value {{
    font-family: "Libre Baskerville", Georgia, serif;
    font-size: 1.15rem;
    line-height: 1.18;
    color: var(--ink) !important;
}}
.signal-chart-wrap {{
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 0.35rem 0.25rem 0.25rem 0.25rem;
    background: linear-gradient(180deg, transparent 0%, {p}07 100%);
}}
.signal-chart {{
    width: 100%;
    height: 225px;
}}
.signal-axis {{
    stroke: var(--line);
    stroke-width: 1;
}}
.signal-tick {{
    stroke: var(--line);
    stroke-width: 1;
    stroke-dasharray: 2 2;
}}
.signal-row {{
    stroke: {p}99;
    stroke-width: 2.2;
}}
.signal-dot {{
    fill: {p};
    stroke: #fff;
    stroke-width: 1.2;
}}
.signal-label {{
    fill: var(--muted);
    font-size: 12px;
    font-family: "Source Sans 3", sans-serif;
}}
.signal-value {{
    fill: var(--ink);
    font-size: 12px;
    font-family: "IBM Plex Mono", monospace;
}}
.signal-spark {{
    fill: none;
    stroke: {s};
    stroke-width: 2;
}}
.signal-spark-dot {{
    fill: {s};
}}

@media (max-width: 950px) {{
    .signal-grid {{
        grid-template-columns: 1fr;
    }}
}}
</style>
"""


def build_visual_overrides_awwwards(theme: dict, dark: bool) -> str:
    p = theme["primary_color"]
    s = theme["secondary_color"]
    if dark:
        paper = "#070B14"
        panel = "#10192A"
        panel_alt = "#17253C"
        text = "#EDF4FF"
        muted = "#9AACCA"
        border = "rgba(181, 205, 240, 0.22)"
        shadow = "rgba(2, 7, 14, 0.55)"
        veil = "rgba(7, 11, 20, 0.74)"
    else:
        paper = "#EDE8DE"
        panel = "#F9F5ED"
        panel_alt = "#F2EBDD"
        text = "#1B2532"
        muted = "#5F6F83"
        border = "rgba(27, 37, 50, 0.16)"
        shadow = "rgba(61, 64, 70, 0.22)"
        veil = "rgba(237, 232, 222, 0.84)"

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');

:root {{
    --paper: {paper};
    --panel: {panel};
    --panel-alt: {panel_alt};
    --ink: {text};
    --muted: {muted};
    --line: {border};
    --shadow: {shadow};
    --veil: {veil};
}}

.stApp {{
    background:
        radial-gradient(1300px 740px at -6% -16%, {p}2E 0%, transparent 58%),
        radial-gradient(980px 560px at 104% -10%, {s}2B 0%, transparent 62%),
        radial-gradient(840px 470px at 42% 110%, {p}17 0%, transparent 68%),
        linear-gradient(160deg, {paper} 0%, {panel_alt} 64%, {paper} 100%) !important;
    background-attachment: fixed !important;
    animation: aurora-drift 18s ease-in-out infinite alternate;
}}
.main {{
    background: transparent !important;
    padding-top: 1.2rem !important;
}}

html, body, .stApp, .stMarkdown, .stButton button, .stTextInput, .stSelectbox, .stChatInput {{
    font-family: "Manrope", "Segoe UI", sans-serif !important;
}}
h1, h2, h3, .hero-title, .section-label {{
    font-family: "Space Grotesk", "Segoe UI", sans-serif !important;
    letter-spacing: -0.012em;
}}
code, pre, .stCodeBlock, .stJson {{
    font-family: "JetBrains Mono", ui-monospace, monospace !important;
}}

p, span, li, label, .stMarkdown p, .stMarkdown li {{
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}}
.msg-ts, .chip-intro, .split-subhead, .relevance-note, .bookmark-meta {{
    color: var(--muted) !important;
    -webkit-text-fill-color: var(--muted) !important;
}}

.hero-shell {{
    border: 1px solid var(--line) !important;
    border-radius: 24px !important;
    background: linear-gradient(150deg, {panel}D8 0%, {panel_alt}F2 100%) !important;
    box-shadow: 0 28px 44px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.13);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    overflow: hidden;
    animation: hero-rise 0.7s ease both;
}}
.hero-shell::after {{
    content: "";
    position: absolute;
    inset: 0;
    background:
        linear-gradient(128deg, transparent 0%, transparent 48%, {s}12 100%),
        radial-gradient(460px 190px at 88% 0%, {p}1F 0%, transparent 72%);
    pointer-events: none;
}}
.hero-kicker {{
    border: 1px solid {p}88 !important;
    background: linear-gradient(135deg, {p}2E 0%, {s}1A 100%) !important;
    color: var(--ink) !important;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
}}
.hero-title {{
    font-size: clamp(1.85rem, 2.5vw, 2.65rem) !important;
    line-height: 1.06 !important;
    letter-spacing: -0.02em !important;
}}
.hero-sub {{
    color: var(--muted) !important;
    max-width: 68ch;
}}

.stChatMessage, .answer-card, .source-rail, .helper-card, .bookmark-card {{
    border: 1px solid var(--line) !important;
    border-radius: 18px !important;
    background: linear-gradient(160deg, {panel}D0 0%, {panel_alt}EF 100%) !important;
    box-shadow: 0 18px 30px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.10);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
}}
.answer-section {{
    border-left: 3px solid {p} !important;
    border-radius: 14px !important;
    background: linear-gradient(120deg, {p}14 0%, transparent 74%) !important;
}}
.section-label {{
    color: {p} !important;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
}}
.source-excerpt, .quote-card {{
    border: 1px solid var(--line) !important;
    border-radius: 14px !important;
    background: linear-gradient(130deg, {p}10 0%, transparent 67%) !important;
}}

div[data-testid="stButton"] button {{
    border-radius: 999px !important;
    border: 1px solid var(--line) !important;
    background: linear-gradient(180deg, {panel}D6 0%, {panel_alt}EA 100%) !important;
    color: var(--ink) !important;
    transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease, background 0.16s ease;
    min-height: 2.65rem;
    font-weight: 650 !important;
}}
div[data-testid="stButton"] button:hover {{
    border-color: {p}88 !important;
    background: linear-gradient(180deg, {p}24 0%, {panel_alt}E4 100%) !important;
    transform: translateY(-1px) scale(1.01);
    box-shadow: 0 10px 24px var(--shadow);
}}
div[data-testid="stButton"] button[kind="primary"] {{
    border: none !important;
    color: #fff !important;
    background: linear-gradient(135deg, {p} 0%, {s} 100%) !important;
    box-shadow: 0 12px 24px {p}44;
}}
div[data-testid="stButton"] button:focus {{
    outline: none !important;
    box-shadow: 0 0 0 3px {p}33 !important;
}}

div[data-testid="stExpander"] {{
    border: 1px solid var(--line) !important;
    border-radius: 16px !important;
    background: linear-gradient(155deg, {panel}CC 0%, {panel_alt}F0 100%) !important;
    box-shadow: 0 16px 28px var(--shadow);
    overflow: hidden;
}}
div[data-testid="stExpander"] summary {{
    font-family: "Space Grotesk", sans-serif !important;
    font-weight: 600 !important;
}}

div[data-testid="stChatInput"] {{
    border: 1px solid var(--line) !important;
    border-radius: 16px !important;
    background: linear-gradient(155deg, {panel}CC 0%, {panel_alt}F0 100%) !important;
    box-shadow: 0 16px 28px var(--shadow) !important;
    overflow: hidden !important;
    transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease !important;
}}
div[data-testid="stChatInput"]:hover {{
    border-color: {p}88 !important;
    box-shadow: 0 18px 30px var(--shadow) !important;
}}
div[data-testid="stChatInput"]:focus-within {{
    border-color: {p} !important;
    box-shadow: 0 0 0 3px {p}24, 0 18px 30px var(--shadow) !important;
}}
div[data-testid="stChatInput"] > div {{
    background: transparent !important;
    border-radius: 16px !important;
    border: none !important;
}}
div[data-testid="stChatInput"] [data-baseweb="textarea"],
div[data-testid="stChatInput"] [data-baseweb="textarea"] > div,
div[data-testid="stChatInput"] .st-bh,
div[data-testid="stChatInput"] .st-bg,
div[data-testid="stChatInput"] .st-bi,
div[data-testid="stChatInput"] .st-bj {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    border-radius: 14px !important;
}}
.stChatFloatingInputContainer,
[data-testid="stChatInputContainer"],
[data-testid="stBottomBlockContainer"],
[data-testid="stBottomBlockContainer"] > div,
[data-testid="stBottom"],
section[data-testid="stBottom"],
section[data-testid="stBottom"] > div {{
    background: var(--veil) !important;
    box-shadow: none !important;
    border: none !important;
}}
.stChatInputContainer {{
    background: var(--veil) !important;
    border: none !important;
}}
[data-testid="stChatInputContainer"] > div,
[data-testid="stChatInputContainer"] > div > div {{
    background: transparent !important;
}}
div[data-testid="stChatInput"] textarea,
.stChatInputContainer textarea,
[data-baseweb="textarea"] textarea {{
    background: transparent !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}}
div[data-testid="stChatInput"] textarea::placeholder,
.stChatInputContainer textarea::placeholder {{
    color: var(--muted) !important;
    -webkit-text-fill-color: var(--muted) !important;
}}

[data-testid="stSidebar"], [data-testid="collapsedControl"] {{
    display: none !important;
}}
footer {{
    display: none !important;
}}

.mobile-nav {{
    border: 1px solid var(--line) !important;
    background: linear-gradient(145deg, {p}AA 0%, {s}AA 100%) !important;
    box-shadow: 0 12px 26px var(--shadow);
}}
.mobile-nav a {{
    color: #fff !important;
    font-family: "Space Grotesk", sans-serif !important;
}}

.sys-shell {{
    position: relative;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 1.05rem 1.05rem 1rem 1.05rem;
    margin: 0.42rem 0 0.92rem 0;
    background:
        radial-gradient(560px 180px at 92% -20%, {s}2F 0%, transparent 68%),
        radial-gradient(480px 220px at -12% 110%, {p}28 0%, transparent 74%),
        linear-gradient(150deg, {panel}CC 0%, {panel_alt}F2 100%);
    box-shadow: 0 16px 34px var(--shadow), inset 0 1px 0 rgba(255,255,255,0.12);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    animation: hero-rise 0.62s ease both;
}}
.sys-shell::after {{
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: linear-gradient(128deg, transparent 0%, transparent 52%, {p}10 100%);
}}
.sys-nav {{
    position: relative;
    z-index: 1;
    display: flex;
    flex-wrap: wrap;
    gap: 0.36rem;
    margin-bottom: 0.72rem;
}}
.sys-nav-pill {{
    font-family: "JetBrains Mono", monospace;
    font-size: 0.67rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 0.16rem 0.52rem;
    color: var(--muted) !important;
    background: {paper}66;
}}
.sys-headline {{
    position: relative;
    z-index: 1;
    font-family: "JetBrains Mono", monospace;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.68rem;
    color: var(--muted) !important;
    margin-bottom: 0.3rem;
}}
.sys-title {{
    position: relative;
    z-index: 1;
    font-family: "Space Grotesk", sans-serif;
    font-size: clamp(1.3rem, 2.05vw, 1.85rem);
    font-weight: 700;
    line-height: 1.04;
    color: var(--ink) !important;
}}
.sys-subline {{
    position: relative;
    z-index: 1;
    margin-top: 0.22rem;
    font-size: 0.84rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted) !important;
}}
.sys-metrics {{
    position: relative;
    z-index: 1;
    margin-top: 0.68rem;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.46rem;
}}
.sys-metrics span {{
    display: block;
    border: 1px solid var(--line);
    border-radius: 11px;
    padding: 0.42rem 0.5rem;
    font-family: "JetBrains Mono", monospace;
    font-size: 0.76rem;
    letter-spacing: 0.05em;
    color: var(--ink) !important;
    background: {paper}54;
    text-align: center;
}}

.pending-query-banner {{
    display: flex;
    align-items: center;
    gap: 0.7rem;
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 0.62rem 0.85rem;
    margin: 0.55rem 0 0.85rem 0;
    background: linear-gradient(135deg, {p}1D 0%, {s}1B 100%);
    box-shadow: 0 10px 20px var(--shadow);
}}
.pending-query-dot {{
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: {p};
    box-shadow: 0 0 0 0 {p}55;
    animation: pending-pulse 1.1s ease-out infinite;
}}
.pending-query-text {{
    font-size: 0.92rem;
    color: var(--ink) !important;
    font-weight: 600;
}}
.pending-query-text strong {{
    font-family: "Space Grotesk", sans-serif;
    letter-spacing: 0.02em;
}}
.status-timeline {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.45rem;
    margin: 0.5rem 0 0.75rem 0;
}}
.status-step {{
    font-size: 0.73rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 0.22rem 0.62rem;
    color: var(--muted) !important;
    background: transparent;
}}
.status-step.status-active {{
    color: var(--ink) !important;
    background: linear-gradient(135deg, {p}28 0%, {s}1B 100%);
    border-color: {p}88;
}}
.status-step.status-done {{
    color: var(--ink) !important;
    border-color: {s}77;
    background: {s}1A;
}}
.status-detail {{
    width: 100%;
    font-size: 0.85rem;
    color: var(--muted) !important;
}}
.citation-chip-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.45rem;
}}
.citation-chip {{
    text-decoration: none !important;
    font-size: 0.74rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 0.2rem 0.58rem;
    background: linear-gradient(135deg, {p}16 0%, {s}12 100%);
    color: var(--ink) !important;
}}
.citation-chip:hover {{
    border-color: {p}88;
    background: linear-gradient(135deg, {p}28 0%, {s}1F 100%);
}}
.source-anchor-block {{
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 0.62rem 0.72rem;
    margin-bottom: 0.58rem;
    background: linear-gradient(135deg, {p}10 0%, transparent 72%);
}}

@media (max-width: 900px) {{
    .sys-shell {{
        padding: 0.92rem 0.84rem;
    }}
    .sys-metrics {{
        grid-template-columns: 1fr;
    }}
}}

@keyframes hero-rise {{
    from {{ transform: translateY(8px); opacity: 0.62; }}
    to {{ transform: translateY(0); opacity: 1; }}
}}
@keyframes aurora-drift {{
    0% {{ filter: saturate(1) hue-rotate(0deg); }}
    100% {{ filter: saturate(1.08) hue-rotate(-6deg); }}
}}
@keyframes pending-pulse {{
    0% {{ box-shadow: 0 0 0 0 {p}55; opacity: 1; }}
    100% {{ box-shadow: 0 0 0 10px transparent; opacity: 0.85; }}
}}
</style>
"""

st.markdown(build_css(THEMES[st.session_state.mode], st.session_state.dark_mode), unsafe_allow_html=True)
st.markdown(build_visual_overrides_awwwards(THEMES[st.session_state.mode], st.session_state.dark_mode), unsafe_allow_html=True)

# Auto-scroll JS (mobile)
st.markdown("""
<script>
function getChatInput(){
  return document.querySelector('[data-testid="stChatInput"] textarea, .stChatInputContainer textarea');
}
function focusChatInput(){
  const input = getChatInput();
  if(input){ input.focus(); }
}
function scrollToBottom(){
  if(window.innerWidth <= 768){
    setTimeout(()=>window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'}),120);
  }
}
function clickMode(label){
  const buttons = Array.from(document.querySelectorAll('button'));
  const hit = buttons.find(btn => btn.innerText && btn.innerText.trim() === label);
  if(hit){ hit.click(); return true; }
  return false;
}
function clickSend(){
  const buttons = Array.from(document.querySelectorAll('button'));
  const send = buttons.find(btn => {
    const t = (btn.innerText || "").trim().toLowerCase();
    const a = (btn.getAttribute('aria-label') || "").trim().toLowerCase();
    return t === "send" || a.includes("send");
  });
  if(send){ send.click(); return true; }
  return false;
}

document.addEventListener('keydown', (e) => {
  const active = document.activeElement;
  const typing = active && (active.tagName === "TEXTAREA" || active.tagName === "INPUT");
  if((e.metaKey || e.ctrlKey) && e.key === 'Enter'){
    if(clickSend()){
      e.preventDefault();
    }
  }
  if(!typing && !e.metaKey && !e.ctrlKey && !e.altKey){
    if(e.key === '1' && clickMode('Rulebook')){
      e.preventDefault();
    }
    if(e.key === '2' && clickMode('CBA')){
      e.preventDefault();
    }
  }
});

const obs = new MutationObserver(() => {
  scrollToBottom();
  setTimeout(focusChatInput, 40);
});
window.addEventListener('load', () => {
  const n = document.querySelector('.main');
  if(n) obs.observe(n, {childList:true,subtree:true});
  scrollToBottom();
  setTimeout(focusChatInput, 220);
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
    if mode == "both":
        return {
            "kb_id": "",
            "model_arn": DEFAULT_MODEL_ARNS["rulebook"],
            "quiz_model_id": DEFAULT_QUIZ_MODEL_ID,
            "region": get_aws_region(),
        }

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


def dedupe_citations(citations: list) -> list:
    seen, unique = set(), []
    for citation in citations or []:
        fingerprint = (
            citation.get("content", "").strip()[:150],
            citation.get("uri", "").split("#")[0],
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(citation)
    return unique


def citation_title(citation: dict, mode: str) -> str:
    metadata = citation.get("metadata", {})
    loc_parts = [
        f"{key.title()} {metadata[key]}"
        for key in ["rule", "section", "article", "part", "page"]
        if key in metadata
    ]
    base = ", ".join(loc_parts) if loc_parts else citation.get("uri", "Source").split("/")[-1][:48]
    source_domain = citation.get("source_domain")
    if source_domain == "rulebook":
        return f"🏀 {base}"
    if source_domain == "cba":
        return f"💰 {base}"
    if mode == "cba":
        badge_label, _, _ = identify_cba_source(citation.get("uri", ""))
        return f"{badge_label} - {base}"
    return base


def render_answer_sections(text: str, citations: list, mode: str, message_key: str):
    unique_citations = dedupe_citations(citations)
    for title, body in parse_answer_sections(text).items():
        chips_html = ""
        if title == "Answer" and unique_citations:
            chips = []
            for idx, citation in enumerate(unique_citations[:4]):
                chips.append(
                    f'<a class="citation-chip" href="#source-{message_key}-{idx}">[{idx + 1}] {html_safe(citation_title(citation, mode))}</a>'
                )
            chips_html = f'<div class="citation-chip-row">{"".join(chips)}</div>'
        st.markdown(
            f'<div class="answer-section"><div class="section-label">{html_safe(title)}</div>{html_safe(body)}{chips_html}</div>',
            unsafe_allow_html=True,
        )


def render_reformulation_box(question: str, mode: str, message_key: str):
    suggestions = suggest_reformulations(question, mode)
    st.markdown(
        '<div class="helper-card"><div class="section-label">Try a narrower follow-up</div></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(suggestions))
    for idx, suggestion in enumerate(suggestions):
        with cols[idx]:
            if st.button(suggestion[:28] + ("..." if len(suggestion) > 28 else ""), key=f"retry_{message_key}_{idx}", use_container_width=True):
                queue_prompt(mode, suggestion)
                st.rerun()


def render_source_panel(msg: dict, mode: str, message_key: str):
    citations = dedupe_citations(msg.get("citations", []))
    st.markdown('<div class="source-rail">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Source Navigator</div>', unsafe_allow_html=True)
    if not citations:
        st.caption("No confidently matched excerpts are attached to this answer.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    conf_label, conf_color = get_confidence(citations)
    st.markdown(
        f'<span class="conf-badge" style="background:{conf_color}22;color:{conf_color};'
        f'border:1px solid {conf_color};">Confidence: {conf_label}</span>',
        unsafe_allow_html=True,
    )
    spotlight_idx = st.selectbox(
        "Detailed source view",
        options=list(range(len(citations))),
        format_func=lambda idx: f"[{idx + 1}] {citation_title(citations[idx], mode)}",
        key=f"spotlight_{message_key}",
    )
    citation = citations[spotlight_idx]
    content = citation.get("content", "No content available")

    tabs = st.tabs(["Navigator", "Exact clause", "Answer vs source"])
    with tabs[0]:
        for idx, source in enumerate(citations):
            source_mode = source.get("source_domain")
            match_terms = source.get("match_terms", [])
            source_text = source.get("content", "No content available")
            preview = source_text[:280] + ("…" if len(source_text) > 280 else "")
            lane_note = ""
            if source_mode and mode == "both":
                lane_note = "Rulebook lane" if source_mode == "rulebook" else "CBA / Operations lane"
            st.markdown(
                f'<div id="source-{message_key}-{idx}" class="source-anchor-block">'
                f'<div class="split-subhead"><strong>[{idx + 1}] {html_safe(citation_title(source, mode))}</strong>'
                f'{" · " + lane_note if lane_note else ""}</div>'
                f'<div class="source-excerpt">{html_safe(preview)}</div>'
                "</div>",
                unsafe_allow_html=True,
            )
            if match_terms:
                st.caption(f"Matched terms: {', '.join(match_terms)}")
    with tabs[1]:
        st.markdown(f'<div class="quote-card">{html_safe(content)}</div>', unsafe_allow_html=True)
        st.code(content, language=None)
    with tabs[2]:
        compare_left, compare_right = st.columns(2)
        with compare_left:
            st.markdown('<div class="section-label">Answer snapshot</div>', unsafe_allow_html=True)
            sections = parse_answer_sections(msg.get("content", ""))
            st.markdown(safe_markdown(sections.get("Answer", msg.get("content", ""))))
        with compare_right:
            st.markdown('<div class="section-label">Exact source text</div>', unsafe_allow_html=True)
            st.markdown(safe_markdown(content))
    st.markdown("</div>", unsafe_allow_html=True)


def render_message_controls(msg: dict, mode: str, message_key: str):
    st.markdown('<div class="split-subhead">Follow-up transforms</div>', unsafe_allow_html=True)
    controls = st.columns(5)
    for idx, (action_key, label) in enumerate(FOLLOWUP_ACTIONS.items()):
        with controls[idx]:
            if st.button(label, key=f"follow_{message_key}_{action_key}", use_container_width=True):
                queue_prompt(mode, build_followup_prompt(action_key, msg, mode), action_key=action_key)
                st.rerun()

    if st.button("Re-run With Stricter Grounding", key=f"strict_rerun_{message_key}", use_container_width=True):
        base_question = msg.get("question") or msg.get("content", "")
        if base_question.strip():
            queue_prompt(
                mode,
                base_question.strip(),
                origin="strict_rerun",
                label="Strict grounding rerun",
                retrieval_overrides={
                    "strict_grounding": True,
                    "exact_match_bias": True,
                    "number_of_results": 8,
                    "max_sources": 5,
                },
            )
            st.rerun()

    utility_cols = st.columns(4)
    with utility_cols[0]:
        if st.button("Save", key=f"save_{message_key}", use_container_width=True):
            save_bookmark(mode, msg)
            st.rerun()
    with utility_cols[1]:
        if st.button("Helpful", key=f"fb_good_{message_key}", use_container_width=True):
            record_feedback(mode, message_key, "Helpful")
            st.rerun()
    with utility_cols[2]:
        if st.button("Unclear", key=f"fb_unclear_{message_key}", use_container_width=True):
            record_feedback(mode, message_key, "Unclear")
            st.rerun()
    with utility_cols[3]:
        if st.button("Wrong citation", key=f"fb_citation_{message_key}", use_container_width=True):
            record_feedback(mode, message_key, "Wrong citation")
            st.rerun()

    feedback = get_feedback_store(mode).get(message_key)
    if feedback:
        st.markdown(f'<span class="feedback-pill">Feedback: {feedback["label"]}</span>', unsafe_allow_html=True)


def render_assistant_message(msg: dict, mode: str):
    message_key = get_message_id(msg)
    left_col, right_col = st.columns([1.8, 1.15], gap="large")
    with left_col:
        st.markdown('<div class="answer-card">', unsafe_allow_html=True)
        if msg.get("timestamp"):
            st.markdown(f'<div class="msg-ts">🕐 {msg["timestamp"]}</div>', unsafe_allow_html=True)
        render_answer_sections(msg["content"], msg.get("citations", []), mode, message_key)
        render_message_controls(msg, mode, message_key)
        with st.expander("📋 Copy response"):
            st.code(msg["content"], language=None)
        if needs_reformulation(msg.get("content", ""), msg.get("citations", [])):
            render_reformulation_box(msg.get("question", "this topic"), mode, message_key)
        if msg.get("cross_mode") and mode != "both":
            other = msg["cross_mode"]
            ot = THEMES[other]
            st.markdown(
                f'<div class="cross-mode-box">💡 <strong>Did you know?</strong> '
                f"This topic also has implications in <strong>{ot['name']}</strong>. "
                f"Switch modes to explore further!</div>",
                unsafe_allow_html=True,
            )
            if st.button(f"Switch to {ot['name']} →", key=f"switch_saved_{message_key}", use_container_width=True):
                st.session_state.mode = other
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    with right_col:
        render_source_panel(msg, mode, message_key)


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

def _citation_match_details(citation: dict, question: str, exact_match_bias: bool = False):
    """
    Return (score, matched_terms) describing why a citation matched the question.
    """
    def keywords(text: str) -> set:
        tokens = re.findall(r"[a-z]+", text.lower())
        return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}

    q_kw = keywords(question)
    if not q_kw:
        return 0.0, []

    metadata = " ".join(f"{k} {v}" for k, v in citation.get("metadata", {}).items())
    cit_kw = keywords(f"{citation.get('content', '')} {metadata} {citation.get('uri', '')}")

    if not cit_kw:
        return 0.0, []

    overlap_score = len(cit_kw & q_kw) / len(q_kw)
    matched_terms = sorted(cit_kw & q_kw)
    phrase_bonus = 0.0

    question_lower = question.lower()
    content_lower = citation.get("content", "").lower()
    uri_lower = citation.get("uri", "").lower()
    for phrase in re.findall(r"[a-z]+(?:\s+[a-z]+)+", question_lower):
        if len(phrase.split()) >= 2 and (phrase in content_lower or phrase in uri_lower):
            phrase_bonus = max(phrase_bonus, 0.15)

    exact_bonus = 0.08 if exact_match_bias and matched_terms else 0.0
    return min(overlap_score + phrase_bonus + exact_bonus, 1.0), matched_terms[:6]


def filter_relevant_citations(citations: list, question: str,
                               min_score: float = 0.08, max_sources: int = 4,
                               exact_match_bias: bool = False) -> list:
    """
    Keep only citations that are meaningfully relevant to the user's question.
    Returns an empty list when no citation clears the relevance threshold.
    """
    if not citations:
        return []

    scored = []
    threshold = min_score + (0.02 if exact_match_bias else 0.0)
    for citation in citations:
        score, match_terms = _citation_match_details(citation, question, exact_match_bias)
        annotated = {
            **citation,
            "match_score": round(score, 3),
            "match_terms": match_terms,
        }
        scored.append((annotated, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    kept = []
    for c, score in scored:
        if score >= threshold and len(kept) < max_sources:
            kept.append(c)

    return kept


def build_query_prompt(question: str, mode: str, retrieval_settings: dict) -> str:
    exact_clause_instruction = (
        "Prioritize exact clause language, definitions, and headings that reuse the user's terms."
        if retrieval_settings.get("exact_match_bias")
        else "Use the most directly relevant sources even when several related sections appear."
    )
    inference_instruction = (
        "If the retrieved material does not directly resolve the question, say that plainly and stop at the closest supported answer."
        if retrieval_settings.get("strict_grounding", True)
        else "If needed, include careful inference, but label it clearly and keep it narrower than the direct source support."
    )
    if mode == "rulebook":
        domain_intro = "You are an expert NBA rules analyst with deep knowledge of basketball regulations."
        mode_instructions = [
            "Use only the retrieved rulebook sources provided by the knowledge base to answer the following question.",
            "For comparisons or scenarios, reason step by step from the cited rules and note any ambiguity that remains.",
            "Cite specific rules and sections only when they are supported by the retrieved material.",
            "Do not invent rule numbers, penalties, dollar figures, or procedures.",
        ]
    else:
        operations_instruction = (
            "Prefer the CBA document and use the Operations Manual only when it is directly relevant."
            if not retrieval_settings.get("include_operations_manual", True)
            else "Use both the CBA and Operations Manual when relevant, and label which source each point comes from."
        )
        domain_intro = "You are an expert on the NBA Collective Bargaining Agreement (CBA) and the NBA Basketball Operations Manual."
        mode_instructions = [
            "Use only the retrieved sources provided by the knowledge base to answer the following question.",
            operations_instruction,
            "Explain how multiple CBA articles or salary-cap rules interact when relevant, but distinguish direct support from inference.",
            "Translate complex financial terms into plain language.",
            "Do not invent article numbers, salary figures, percentages, or procedural details.",
        ]

    mode_instruction_lines = "\n".join(
        f"{idx}. {line}"
        for idx, line in enumerate(mode_instructions, start=5)
    )

    return f"""{domain_intro}
Question: {question}

Instructions:
1. Base the answer on retrieved sources and prior conversation context only when that context remains consistent with the sources.
2. {inference_instruction}
3. Use this exact answer structure:
   Answer:
   Direct source support:
   Careful inference (if any):
4. {exact_clause_instruction}
{mode_instruction_lines}

Begin your answer now using the required headings.
Answer:
"""


def run_retrieve_and_generate(client, params: dict):
    """Call Bedrock retrieve_and_generate, retrying without unsupported retrieval tuning fields."""
    try:
        return client.retrieve_and_generate(**params)
    except ParamValidationError as e:
        message = str(e)
        if (
            "retrievalConfiguration" in message
            or "vectorSearchConfiguration" in message
            or "numberOfResults" in message
        ):
            params["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"].pop("retrievalConfiguration", None)
            return client.retrieve_and_generate(**params)
        raise


def query_knowledge_base(question: str, knowledge_base_id: str, model_arn: str,
                          mode: str = "rulebook", session_id: str = None,
                          region_name: str = None, retrieval_settings: dict = None):
    """Query Bedrock Knowledge Base. Returns (response_text, citations, session_id)."""
    client = get_bedrock_client("bedrock-agent-runtime", region_name)
    if not client:
        return "Error: Could not initialise Bedrock client.", [], None

    retrieval_settings = retrieval_settings or _default_retrieval_settings()
    if session_id is None:
        session_id = str(uuid.uuid4())

    prompt = build_query_prompt(question, mode, retrieval_settings)

    params = {
        "input": {"text": prompt},
        "retrieveAndGenerateConfiguration": {
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": knowledge_base_id,
                "modelArn": model_arn,
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": retrieval_settings.get("number_of_results", 5),
                    }
                },
            },
        },
    }
    if session_id:
        params["sessionId"] = session_id

    try:
        resp              = run_retrieve_and_generate(client, params)
        new_session_id    = resp.get("sessionId", session_id)
        generated_text    = resp["output"]["text"]
        citations         = _extract_citations(resp)
        citations         = filter_relevant_citations(
            citations,
            question,
            max_sources=retrieval_settings.get("max_sources", 4),
            exact_match_bias=retrieval_settings.get("exact_match_bias", False),
        )
        return generated_text, citations, new_session_id

    except ClientError as e:
        code    = e.response["Error"]["Code"]
        message = e.response["Error"]["Message"]

        if code == "ValidationException" and (
            "retrievalConfiguration" in message
            or "vectorSearchConfiguration" in message
            or "numberOfResults" in message
        ):
            params["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"].pop("retrievalConfiguration", None)
            try:
                resp = run_retrieve_and_generate(client, params)
                new_session_id = resp.get("sessionId", session_id)
                gen_text = resp["output"]["text"]
                cits = filter_relevant_citations(
                    _extract_citations(resp),
                    question,
                    max_sources=retrieval_settings.get("max_sources", 4),
                    exact_match_bias=retrieval_settings.get("exact_match_bias", False),
                )
                return gen_text, cits, new_session_id
            except Exception as retry_err:
                return f"Retry failed: {retry_err}", [], None

        # Retry without session if session/config is stale
        if code == "ValidationException" and (
            "Knowledge base configurations cannot be modified" in message
            or "Session" in message
        ):
            params.pop("sessionId", None)
            try:
                resp           = run_retrieve_and_generate(client, params)
                new_session_id = resp.get("sessionId")
                gen_text       = resp["output"]["text"]
                cits           = filter_relevant_citations(
                    _extract_citations(resp),
                    question,
                    max_sources=retrieval_settings.get("max_sources", 4),
                    exact_match_bias=retrieval_settings.get("exact_match_bias", False),
                )
                return gen_text, cits, new_session_id
            except Exception as retry_err:
                return f"Retry failed: {retry_err}", [], None

        return f"AWS Error ({code}): {message}", [], session_id

    except ParamValidationError as e:
        return f"Error querying knowledge base: {e}", [], session_id

    except Exception as e:
        return f"Error querying knowledge base: {e}", [], session_id


def is_low_signal_chunk(text: str) -> bool:
    lower = text.lower().strip()
    if not lower:
        return True
    if "table of contents" in lower:
        return True

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    toc_like = 0
    for line in lines:
        if "..." in line or re.match(r"^(rule|section|article|part)\b", line.lower()):
            toc_like += 1
    return len(lines) >= 3 and toc_like >= max(3, int(len(lines) * 0.6))


def build_manual_retrieval_queries(question: str, mode: str) -> list:
    queries = [question]
    expanded = expand_query_for_retrieval(question, mode)
    if expanded != question and "Retrieval hints:" in expanded:
        queries.append(expanded.split("Retrieval hints:", 1)[1].replace(";", " "))

    lower = question.lower()
    if mode == "rulebook" and "foul" in lower and "violation" in lower:
        queries.extend([
            "foul definition nba rulebook",
            "violation definition nba rulebook",
            "personal foul definition rulebook",
            "technical foul definition rulebook",
        ])

    unique = []
    seen = set()
    for query in queries:
        cleaned = query.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique[:3]


def build_manual_answer_prompt(question: str, mode: str, retrieval_settings: dict, source_text: str) -> str:
    base_prompt = build_query_prompt(question, mode, retrieval_settings).rsplit("Answer:", 1)[0].rstrip()
    return (
        f"{base_prompt}\n\n"
        "Use ONLY the source excerpts below. Do not rely on outside knowledge. "
        "If the excerpts still do not contain enough information, say exactly what is missing.\n\n"
        f"SOURCE EXCERPTS:\n{source_text}\n\n"
        "Answer:"
    )


def manual_retrieve_and_answer(question: str, knowledge_base_id: str, model_arn: str,
                               mode: str, region_name: str, retrieval_settings: dict):
    rag_client = get_bedrock_client("bedrock-agent-runtime", region_name)
    runtime_client = get_bedrock_runtime_client(region_name)
    if not rag_client or not runtime_client:
        return None, []

    raw_citations = []
    seen = set()
    for retrieval_query in build_manual_retrieval_queries(question, mode):
        try:
            retrieval_resp = rag_client.retrieve(
                knowledgeBaseId=knowledge_base_id,
                retrievalQuery={"text": retrieval_query},
                retrievalConfiguration={
                    "vectorSearchConfiguration": {
                        "numberOfResults": max(retrieval_settings.get("number_of_results", 5), 4),
                    }
                },
            )
        except Exception:
            continue

        for result in retrieval_resp.get("retrievalResults", []):
            text = result.get("content", {}).get("text", "").strip()
            if is_low_signal_chunk(text):
                continue

            location = result.get("location", {}).get("s3Location", {})
            uri = location.get("uri", "Unknown source")
            metadata = result.get("metadata", {})
            fingerprint = (text[:180], uri.split("#")[0])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            raw_citations.append({
                "content": text,
                "uri": uri,
                "metadata": metadata,
            })

    filtered_citations = filter_relevant_citations(
        raw_citations,
        question,
        max_sources=max(retrieval_settings.get("max_sources", 4), 4),
        exact_match_bias=True,
    )
    if not filtered_citations:
        return None, []

    for citation in filtered_citations:
        citation["source_domain"] = mode

    source_blocks = []
    for citation in filtered_citations:
        label = citation_title(citation, mode)
        source_blocks.append(f"[{label}]\n{citation['content']}")
    prompt = build_manual_answer_prompt(question, mode, retrieval_settings, "\n\n---\n\n".join(source_blocks))

    try:
        response = runtime_client.invoke_model(
            modelId=model_arn,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        result = json.loads(response["body"].read())
        text = result.get("content", [{}])[0].get("text", "")
        return text, filtered_citations
    except Exception:
        return None, filtered_citations


def combine_crossbook_answers(question: str, rulebook_text: str, cba_text: str) -> str:
    rulebook_sections = parse_answer_sections(rulebook_text)
    cba_sections = parse_answer_sections(cba_text)
    takeaway_lines = []
    if rulebook_sections.get("Answer"):
        takeaway_lines.append(f"Rulebook: {rulebook_sections['Answer']}")
    if cba_sections.get("Answer"):
        takeaway_lines.append(f"CBA / Operations: {cba_sections['Answer']}")

    direct_support = []
    if rulebook_sections.get("Direct source support"):
        direct_support.append("Rulebook view:\n" + rulebook_sections["Direct source support"])
    if cba_sections.get("Direct source support"):
        direct_support.append("CBA / Operations view:\n" + cba_sections["Direct source support"])

    inference_parts = []
    if rulebook_sections.get("Careful inference"):
        inference_parts.append("Rulebook inference:\n" + rulebook_sections["Careful inference"])
    if cba_sections.get("Careful inference"):
        inference_parts.append("CBA / Operations inference:\n" + cba_sections["Careful inference"])

    answer_block = "\n\n".join(takeaway_lines) if takeaway_lines else (
        "This topic spans both sources, but neither side returned a confident, grounded answer."
    )
    direct_block = "\n\n".join(direct_support) if direct_support else (
        "The retrieved material did not produce strong direct support in one or both source sets."
    )
    inference_block = "\n\n".join(inference_parts) if inference_parts else "No additional inference beyond the direct support."

    return (
        "Answer:\n"
        f"{answer_block}\n\n"
        "Rulebook view:\n"
        f"{rulebook_sections.get('Answer', 'No grounded rulebook answer was returned.')}\n\n"
        "CBA / Operations view:\n"
        f"{cba_sections.get('Answer', 'No grounded CBA / Operations answer was returned.')}\n\n"
        "Direct source support:\n"
        f"{direct_block}\n\n"
        "Careful inference (if any):\n"
        f"{inference_block}\n\n"
        "Takeaway:\n"
        "Use the rulebook for on-court administration and the CBA / Operations materials for roster, contract, discipline, and transaction consequences."
    )


def should_run_manual_fallback(response: str, citations: list) -> bool:
    if not citations:
        return True
    lower = (response or "").lower()
    hard_failure_markers = (
        "unable to assist",
        "error querying knowledge base",
        "aws error",
        "retry failed",
    )
    return any(marker in lower for marker in hard_failure_markers)


def query_app_mode(
    question: str,
    mode: str,
    runtime_config: dict,
    retrieval_settings: dict,
    response_mode: str = "balanced",
    status_cb=None,
):
    profile = RESPONSE_PROFILES.get(response_mode, RESPONSE_PROFILES["balanced"])

    def status(stage: str, detail: str = ""):
        if status_cb:
            status_cb(stage, detail)

    def better_candidate(curr_resp, curr_cits, new_resp, new_cits):
        return (
            bool(new_cits)
            and (
                not curr_cits
                or len(new_cits) > len(curr_cits)
                or not needs_reformulation(new_resp, new_cits)
            )
        )

    if mode in ("rulebook", "cba"):
        cur_session = st.session_state.session_ids.get(mode)
        is_cold_start = cur_session is None and not any(
            msg.get("role") == "assistant" for msg in get_messages(mode)
        )
        session_scope = cur_session or "new"
        cache_key = _cache_key(question, mode, response_mode, retrieval_settings, session_scope)
        cached = _cache_get(mode, cache_key)
        if cached:
            response, citations = cached
            for citation in citations:
                citation["source_domain"] = mode
            status("finalizing", "Loaded from cache")
            return response, citations

        status("retrieving", "Initial retrieval pass")
        first_pass_settings = progressive_first_pass_settings(retrieval_settings, response_mode)
        response, citations, new_session = query_knowledge_base(
            question,
            runtime_config["kb_id"],
            runtime_config["model_arn"],
            mode,
            session_id=cur_session,
            region_name=runtime_config["region"],
            retrieval_settings=first_pass_settings,
        )
        status("ranking", f"{len(citations)} source matches")

        needs_followup = needs_reformulation(response, citations)
        first_pass_differs = (
            first_pass_settings.get("number_of_results") != retrieval_settings.get("number_of_results")
            or first_pass_settings.get("max_sources") != retrieval_settings.get("max_sources")
        )

        if needs_followup and first_pass_differs:
            status("retrieving", "Escalating retrieval depth")
            deep_response, deep_citations, new_session = query_knowledge_base(
                question,
                runtime_config["kb_id"],
                runtime_config["model_arn"],
                mode,
                session_id=new_session,
                region_name=runtime_config["region"],
                retrieval_settings=retrieval_settings,
            )
            if better_candidate(response, citations, deep_response, deep_citations):
                response, citations = deep_response, deep_citations
            needs_followup = needs_reformulation(response, citations)
            status("ranking", f"{len(citations)} source matches")

        allow_expanded_retry = profile.get("allow_expanded_retry", True)
        allow_manual_fallback = profile.get("allow_manual_fallback", True) and should_run_manual_fallback(response, citations)

        # First-turn speed optimization: avoid the slowest fallback path on cold start in Fast/Balanced.
        if is_cold_start and response_mode in ("fast", "balanced"):
            allow_manual_fallback = False
            if citations:
                allow_expanded_retry = False

        expanded_question = question
        run_expanded = False
        if allow_expanded_retry and needs_followup:
            expanded_question = expand_query_for_retrieval(question, mode)
            run_expanded = expanded_question != question

        run_manual = allow_manual_fallback and needs_followup

        if run_expanded or run_manual:
            status("retrieving", "Running fallback retrieval")
            with ThreadPoolExecutor(max_workers=2) as pool:
                retry_future = (
                    pool.submit(
                        query_knowledge_base,
                        expanded_question,
                        runtime_config["kb_id"],
                        runtime_config["model_arn"],
                        mode,
                        new_session,
                        runtime_config["region"],
                        retrieval_settings,
                    )
                    if run_expanded
                    else None
                )
                manual_future = (
                    pool.submit(
                        manual_retrieve_and_answer,
                        question,
                        runtime_config["kb_id"],
                        runtime_config["model_arn"],
                        mode,
                        runtime_config["region"],
                        retrieval_settings,
                    )
                    if run_manual
                    else None
                )

                if retry_future:
                    retry_response, retry_citations, retry_session = retry_future.result()
                    new_session = retry_session
                    if better_candidate(response, citations, retry_response, retry_citations):
                        response, citations = retry_response, retry_citations

                if manual_future:
                    manual_response, manual_citations = manual_future.result()
                    if better_candidate(response, citations, manual_response, manual_citations):
                        response, citations = manual_response, manual_citations

            needs_followup = needs_reformulation(response, citations)
            status("ranking", f"{len(citations)} source matches")

        status("drafting", "Composing grounded answer")
        st.session_state.session_ids[mode] = new_session
        for citation in citations:
            citation["source_domain"] = mode

        final_scope = new_session or session_scope
        final_cache_key = _cache_key(question, mode, response_mode, retrieval_settings, final_scope)
        _cache_set(mode, final_cache_key, response, citations)
        return response, citations

    rulebook_config = get_mode_runtime_config("rulebook")
    cba_config = get_mode_runtime_config("cba")
    rb_session_scope = st.session_state.session_ids.get("both_rulebook") or "new"
    cba_session_scope = st.session_state.session_ids.get("both_cba") or "new"
    cross_scope = f"{rb_session_scope}:{cba_session_scope}"
    cross_cache_key = _cache_key(question, "both", response_mode, retrieval_settings, cross_scope)
    cross_cached = _cache_get("both", cross_cache_key)
    if cross_cached:
        cached_response, cached_citations = cross_cached
        status("finalizing", "Loaded crossbook answer from cache")
        return cached_response, cached_citations

    status("retrieving", "Querying Rulebook and CBA in parallel")
    first_pass_settings = progressive_first_pass_settings(retrieval_settings, response_mode)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rb_future = pool.submit(
            query_knowledge_base,
            question,
            rulebook_config["kb_id"],
            rulebook_config["model_arn"],
            "rulebook",
            st.session_state.session_ids.get("both_rulebook"),
            rulebook_config["region"],
            first_pass_settings,
        )
        cba_future = pool.submit(
            query_knowledge_base,
            question,
            cba_config["kb_id"],
            cba_config["model_arn"],
            "cba",
            st.session_state.session_ids.get("both_cba"),
            cba_config["region"],
            first_pass_settings,
        )
        rb_response, rb_citations, rb_session = rb_future.result()
        cba_response, cba_citations, cba_session = cba_future.result()

    first_pass_differs = (
        first_pass_settings.get("number_of_results") != retrieval_settings.get("number_of_results")
        or first_pass_settings.get("max_sources") != retrieval_settings.get("max_sources")
    )
    rb_weak = needs_reformulation(rb_response, rb_citations)
    cba_weak = needs_reformulation(cba_response, cba_citations)

    if first_pass_differs and (rb_weak or cba_weak):
        status("retrieving", "Escalating weak lane retrieval")
        with ThreadPoolExecutor(max_workers=2) as pool:
            rb_retry_future = (
                pool.submit(
                    query_knowledge_base,
                    question,
                    rulebook_config["kb_id"],
                    rulebook_config["model_arn"],
                    "rulebook",
                    rb_session,
                    rulebook_config["region"],
                    retrieval_settings,
                )
                if rb_weak
                else None
            )
            cba_retry_future = (
                pool.submit(
                    query_knowledge_base,
                    question,
                    cba_config["kb_id"],
                    cba_config["model_arn"],
                    "cba",
                    cba_session,
                    cba_config["region"],
                    retrieval_settings,
                )
                if cba_weak
                else None
            )
            if rb_retry_future:
                rb_new_response, rb_new_citations, rb_session = rb_retry_future.result()
                if better_candidate(rb_response, rb_citations, rb_new_response, rb_new_citations):
                    rb_response, rb_citations = rb_new_response, rb_new_citations
            if cba_retry_future:
                cba_new_response, cba_new_citations, cba_session = cba_retry_future.result()
                if better_candidate(cba_response, cba_citations, cba_new_response, cba_new_citations):
                    cba_response, cba_citations = cba_new_response, cba_new_citations

    status("ranking", f"{len(rb_citations) + len(cba_citations)} combined source matches")
    st.session_state.session_ids["both_rulebook"] = rb_session
    st.session_state.session_ids["both_cba"] = cba_session

    for citation in rb_citations:
        citation["source_domain"] = "rulebook"
    for citation in cba_citations:
        citation["source_domain"] = "cba"

    status("drafting", "Composing crossbook synthesis")
    combined = combine_crossbook_answers(question, rb_response, cba_response)
    merged_citations = rb_citations + cba_citations
    final_cross_scope = f"{rb_session or 'new'}:{cba_session or 'new'}"
    final_cross_key = _cache_key(question, "both", response_mode, retrieval_settings, final_cross_scope)
    _cache_set("both", final_cross_key, combined, merged_citations)
    return combined, merged_citations


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


def render_quick_chips(mode: str):
    st.markdown('<div class="chip-intro">Tap a quick-start topic to jump into the corpus faster.</div>', unsafe_allow_html=True)
    chip_cols = st.columns(3)
    for idx, chip in enumerate(QUICK_CHIPS[mode]):
        with chip_cols[idx % 3]:
            if st.button(chip, key=f"chip_{mode}_{idx}", use_container_width=True):
                prompt = starter_prompt_for(mode, chip)
                queue_prompt(mode, prompt, origin="quick_chip", label=chip)
                st.rerun()


def render_sidebar_bookmarks(mode: str):
    bookmarks = get_bookmarks(mode)
    st.markdown("### 🔖 Bookmarks")
    if not bookmarks:
        st.caption("Save strong answers here for quick return trips.")
        return

    for idx, bookmark in enumerate(bookmarks[-6:][::-1]):
        st.markdown(
            f'<div class="bookmark-card"><strong>{html_safe(bookmark["title"])}</strong>'
            f'<div class="bookmark-meta">{html_safe(bookmark.get("timestamp", ""))}</div></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        with cols[0]:
            if st.button("Open", key=f"bm_open_{mode}_{bookmark['id']}_{idx}", use_container_width=True):
                queue_prompt(mode, bookmark.get("question") or bookmark["title"])
                st.rerun()
        with cols[1]:
            if st.button("Reuse", key=f"bm_reuse_{mode}_{bookmark['id']}_{idx}", use_container_width=True):
                queue_prompt(mode, f"Revisit this topic and update the answer with fresh citations: {bookmark.get('question') or bookmark['title']}")
                st.rerun()


def render_mobile_nav(current_mode: str):
    links = ['<a href="#query-starters">Starters</a>']
    if current_mode != "both":
        links.append('<a href="#quiz-panel">Quiz</a>')
    if current_mode == "rulebook":
        links.append('<a href="#scenario-panel">Scenario</a>')
    st.markdown(f'<div class="mobile-nav">{"".join(links)}</div>', unsafe_allow_html=True)


def render_system_shell(current_mode: str, active_response_mode: str, current_messages: list, assistant_history: list):
    theme = THEMES[current_mode]
    q_count = sum(1 for msg in current_messages if msg.get("role") == "user")
    cache_count = len(_cache_store(current_mode))

    st.markdown(
        f"""
        <div class="sys-shell">
            <div class="sys-title">{theme["title"]}</div>
            <div class="sys-subline">ALL SYSTEMS OPERATIONAL · MODE {theme["name"]} · PROFILE {RESPONSE_PROFILES[active_response_mode]["label"].upper()}</div>
            <div class="sys-metrics">
                <span>QUESTIONS {q_count}</span>
                <span>ANSWERS {len(assistant_history)}</span>
                <span>CACHE {cache_count}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_metrics(mode: str, question_count: int, answer_count: int, bookmark_count: int, feedback_count: int):
    metrics = [
        ("Questions", question_count),
        ("Answers", answer_count),
        ("Bookmarks", bookmark_count),
        ("Feedback", feedback_count),
    ]
    cards = "".join(
        f"""
        <div class="sidebar-metric">
            <span class="sidebar-metric-label">{html.escape(label)}</span>
            <span class="sidebar-metric-value">{value}</span>
        </div>
        """
        for label, value in metrics
    )
    st.markdown(f'<div class="sidebar-metrics">{cards}</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# EXPORT HELPER
# ─────────────────────────────────────────────
def export_chat(messages: list, mode: str, export_format: str = "Transcript") -> str:
    t = THEMES[mode]
    if export_format == "Transcript":
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

    assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
    user_messages = [msg for msg in messages if msg["role"] == "user"]
    lines = [
        f"# {export_format}",
        f"Mode: {t['name']}",
        f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    if export_format == "Scout note":
        lines += ["## Key Questions"]
        lines += [f"- {msg['content']}" for msg in user_messages[-8:]] or ["- No questions logged yet."]
        lines += ["", "## Takeaways"]
        for msg in assistant_messages[-6:]:
            answer = parse_answer_sections(msg["content"]).get("Answer", msg["content"])
            lines.append(f"- {answer}")
        return "\n".join(lines)

    if export_format == "Cap memo":
        lines += ["## Executive Summary"]
        for msg in assistant_messages[-5:]:
            sections = parse_answer_sections(msg["content"])
            lines.append(f"- Issue: {msg.get('question', 'Prior topic')}")
            lines.append(f"  View: {sections.get('Answer', msg['content'])}")
            if sections.get("Direct source support"):
                lines.append(f"  Support: {sections['Direct source support']}")
            lines.append("")
        return "\n".join(lines)

    lines += ["## Game Ruling Summary"]
    for msg in assistant_messages[-5:]:
        sections = parse_answer_sections(msg["content"])
        lines.append(f"- Situation: {msg.get('question', 'Prior topic')}")
        lines.append(f"  Ruling: {sections.get('Answer', msg['content'])}")
        if sections.get("Direct source support"):
            lines.append(f"  Rule support: {sections['Direct source support']}")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    current_mode = st.session_state.mode
    current_messages = get_messages(current_mode)
    assistant_history = [msg for msg in current_messages if msg.get("role") == "assistant"]
    runtime_config = get_mode_runtime_config(current_mode)
    retrieval_settings = get_retrieval_settings(current_mode)
    theme = THEMES[current_mode]
    kb_id = runtime_config["kb_id"]
    model_arn = runtime_config["model_arn"]
    quiz_model_id = runtime_config["quiz_model_id"]
    active_response_mode = st.session_state.get("response_mode", "balanced")

    # ──────────────────────────────────────────
    # MODE SWITCH
    # ──────────────────────────────────────────
    mode_cols = st.columns([1, 1, 0.22], gap="small")
    with mode_cols[0]:
        if st.button(
            "Rulebook",
            key="mode_switch_rulebook",
            use_container_width=True,
            type="primary" if current_mode == "rulebook" else "secondary",
        ):
            if current_mode != "rulebook":
                st.session_state.mode = "rulebook"
                st.rerun()
    with mode_cols[1]:
        if st.button(
            "CBA",
            key="mode_switch_cba",
            use_container_width=True,
            type="primary" if current_mode == "cba" else "secondary",
        ):
            if current_mode != "cba":
                st.session_state.mode = "cba"
                st.rerun()
    with mode_cols[2]:
        theme_icon = "☀︎" if st.session_state.dark_mode else "☾"
        if st.button(theme_icon, key="theme_toggle_main", use_container_width=True, help="Toggle theme"):
            st.session_state.dark_mode = not st.session_state.dark_mode
            st.rerun()

    profile_cols = st.columns(3, gap="small")
    for idx, profile_key in enumerate(("fast", "balanced", "deep")):
        with profile_cols[idx]:
            if st.button(
                RESPONSE_PROFILES[profile_key]["label"],
                key=f"profile_{profile_key}",
                use_container_width=True,
                type="primary" if active_response_mode == profile_key else "secondary",
            ):
                st.session_state.response_mode = profile_key
                st.rerun()
    st.caption(
        f"Response mode: **{RESPONSE_PROFILES[active_response_mode]['label']}** - "
        f"{RESPONSE_PROFILES[active_response_mode]['description']}"
    )

    # ──────────────────────────────────────────
    # WELCOME (AT TOP WHEN NEW)
    # ──────────────────────────────────────────
    if len(current_messages) == 0:
        st.markdown(
            f"""
            <div style="text-align:center;padding:0.8rem 0 1.2rem 0;">
                <h2 style="color:{theme['primary_color']};margin-bottom:0.35rem;">{theme['icon']} Welcome!</h2>
                <p style="font-size:1.08rem;margin:0;">
                    {"Ask me anything about NBA rules, regulations, and gameplay."
                     if current_mode == "rulebook"
                     else "Ask crossbook questions that connect on-court rules with contracts, roster rules, and league operations."
                     if current_mode == "both"
                     else "Ask me about NBA contracts, salary cap, and league business rules."}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Use the chips and starter prompts below to jump right in.")

    render_system_shell(current_mode, active_response_mode, current_messages, assistant_history)

    pending_prompt = st.session_state.pending_prompts.get(current_mode)
    pending_meta = st.session_state.pending_prompt_meta.get(current_mode) or {}
    if pending_prompt and pending_meta.get("origin") in {"quick_chip", "starter"}:
        label = html.escape(pending_meta.get("label", "Quick query"))
        st.markdown(
            '<div class="pending-query-banner">'
            '<span class="pending-query-dot"></span>'
            f'<span class="pending-query-text">Retrieving results for <strong>{label}</strong>…</span>'
            "</div>",
            unsafe_allow_html=True,
        )

    with st.expander("Session Library", expanded=False):
        lib_left, lib_right = st.columns(2, gap="large")
        with lib_left:
            if st.button("Clear current mode history", key=f"clear_mode_{current_mode}", use_container_width=True):
                clear_mode_state(current_mode)
                st.rerun()
            st.session_state.export_format = st.selectbox(
                "Export style",
                EXPORT_FORMATS,
                index=EXPORT_FORMATS.index(st.session_state.export_format),
                key="export_style",
            )
            if current_messages:
                md_export = export_chat(current_messages, current_mode, st.session_state.export_format)
                ts_str = datetime.now().strftime("%Y%m%d_%H%M")
                st.download_button(
                    label="Download session",
                    data=md_export,
                    file_name=f"nba_{current_mode}_{ts_str}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
        with lib_right:
            render_sidebar_bookmarks(current_mode)

    # ──────────────────────────────────────────
    # HEADER
    # ──────────────────────────────────────────
    st.markdown(
        f'<div class="hero-sub" style="margin:0.2rem 0 0.72rem 0;">{theme["subtitle"]}</div>',
        unsafe_allow_html=True,
    )
    render_mobile_nav(current_mode)

    st.markdown('<div id="query-starters"></div>', unsafe_allow_html=True)
    st.markdown("### ⚡ Query Starters")
    render_quick_chips(current_mode)
    starter_cols = st.columns(2)
    for idx, ex in enumerate(theme["examples"]):
        with starter_cols[idx % 2]:
            if st.button(f"{theme['icon']} {ex}", key=f"starter_{current_mode}_{idx}", use_container_width=True):
                queue_prompt(current_mode, starter_prompt_for(current_mode, ex), origin="starter", label=ex)
                st.rerun()
    st.markdown("---")

    # ──────────────────────────────────────────
    # QUIZ ME
    # ──────────────────────────────────────────
    st.markdown('<div id="quiz-panel"></div>', unsafe_allow_html=True)
    with st.expander("🎯 Quiz Me!", expanded=False):
        if current_mode == "both":
            st.info("Quiz mode is available in single-source views so each question can stay tightly grounded.")
        else:
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
        st.markdown('<div id="scenario-panel"></div>', unsafe_allow_html=True)
        with st.expander("🏀 Scenario Simulator — Get a rules ruling", expanded=False):
            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                play_type  = st.selectbox("Play type", [
                    "Drive to basket", "Three-point attempt", "Post play",
                    "Pick and roll", "Inbound play", "Jump ball", "Free throw", "Other",
                ], key="sim_play")
                game_clock = st.text_input("Game clock (e.g. 0:04)", key="sim_gclk")
                possession_state = st.selectbox(
                    "Possession state",
                    ["Team control", "Loose ball", "Rebound", "Throw-in", "Jump ball", "Unsure"],
                    key="sim_possession",
                )
            with sc2:
                shot_clock = st.selectbox("Shot clock", [
                    "Active (>0)", "Expired (0)", "Not applicable",
                ], key="sim_sclk")
                court_pos  = st.selectbox("Court position", [
                    "Paint/Key", "Mid-range", "Three-point line",
                    "Half court", "Backcourt", "Out-of-bounds area",
                ], key="sim_pos")
                contact_type = st.selectbox(
                    "Contact / foul type",
                    ["No contact", "Incidental contact", "Personal foul", "Loose-ball foul", "Flagrant", "Technical", "Unsure"],
                    key="sim_contact",
                )
            with sc3:
                review_status = st.selectbox(
                    "Replay / challenge status",
                    ["No review", "Coach's challenge available", "Automatic replay trigger", "Under review", "Unsure"],
                    key="sim_review",
                )
                outcome_state = st.selectbox(
                    "Result of play",
                    ["Shot attempt", "Made basket", "Missed basket", "Turnover", "Dead ball", "Timeout / substitution", "Unsure"],
                    key="sim_outcome",
                )

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
                    f"Possession State: {possession_state}\n"
                    f"Contact Type: {contact_type}\n"
                    f"Replay / Challenge Status: {review_status}\n"
                    f"Result of Play: {outcome_state}\n\n"
                    f"Situation: {situation}\n\n"
                    "Please provide a clear ruling on this situation, cite the exact rules that apply, "
                    "and note any replay or procedural wrinkles if they matter."
                )
                st.session_state.pending_prompts[current_mode] = scenario_prompt
                st.rerun()

    # ──────────────────────────────────────────
    # CHAT HISTORY
    # ──────────────────────────────────────────
    if len(current_messages) > 0:
        for idx, msg in enumerate(current_messages):
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    msg.setdefault("id", f"history-{idx}-{get_message_id(msg)}")
                    render_assistant_message(msg, current_mode)
                else:
                    st.markdown(safe_markdown(msg["content"]))
                    if msg.get("timestamp"):
                        st.markdown(f'<div class="msg-ts">🕐 {msg["timestamp"]}</div>', unsafe_allow_html=True)

    # ──────────────────────────────────────────
    # CHAT INPUT
    # ──────────────────────────────────────────
    if current_mode == "rulebook":
        placeholder = "Ask a question about NBA rules…"
    elif current_mode == "both":
        placeholder = "Compare gameplay rules with CBA / operations impacts…"
    else:
        placeholder = "Ask about contracts, salary cap, or CBA rules…"

    typed_prompt = st.chat_input(placeholder)

    # Resolve prompt (typed input wins; fallback to pending)
    prompt = typed_prompt
    pending_prompt = st.session_state.pending_prompts[current_mode]
    queued_action = None
    pending_meta_current = {}
    if not prompt and pending_prompt:
        prompt = pending_prompt
        pending_meta_current = st.session_state.pending_prompt_meta.get(current_mode) or {}
        st.session_state.pending_prompts[current_mode] = None
        queued_action = st.session_state.queued_action[current_mode]
        st.session_state.queued_action[current_mode] = None
        st.session_state.pending_prompt_meta[current_mode] = None
    elif prompt:
        st.session_state.pending_prompt_meta[current_mode] = None

    if prompt:
        ts = datetime.now().strftime("%b %d, %I:%M %p")
        current_messages.append({"id": make_message_id(), "role": "user", "content": prompt, "timestamp": ts})

        with st.chat_message("user"):
            st.markdown(safe_markdown(prompt))
            st.markdown(f'<div class="msg-ts">🕐 {ts}</div>', unsafe_allow_html=True)

        # ── Animated loading card inside the assistant bubble ────────────────────
        status_placeholder = st.empty()
        loading_state = loading_state_for(current_mode)
        loading_icon = loading_state["icon"]
        loading_label = loading_state["label"]
        loading_sub = loading_state["sub"]
        loading_steps_html = "".join(
            f'<span class="thinking-step">{html.escape(step)}</span>'
            for step in loading_state["steps"]
        )
        status_timeline = st.empty()
        loading_card_steps_html = "".join(
            f'<span class="loading-step">{html.escape(step)}</span>'
            for step in loading_state["steps"]
        )
        thinking_banner_html = f"""
<div class="thinking-banner">
    <div class="thinking-title">{loading_label}</div>
    <div class="thinking-sub">{loading_sub}</div>
    <div class="thinking-steps">{loading_steps_html}</div>
    <div class="thinking-track"></div>
</div>"""
        loading_html = f"""
<div class="loading-card">
    <div class="loading-ball">{loading_icon}</div>
    <div class="loading-ring"></div>
    <div class="loading-label">{loading_label}</div>
    <div class="loading-sub">{loading_sub}</div>
    <div class="loading-steps">{loading_card_steps_html}</div>
    <div class="loading-dots" style="margin-top:0.8rem;">
        <span></span><span></span><span></span>
    </div>
</div>"""

        with st.chat_message("assistant"):
            loading_placeholder = st.empty()
            status_timeline.markdown(build_status_timeline_html("retrieving", "Starting retrieval"), unsafe_allow_html=True)
            status_placeholder.markdown(thinking_banner_html, unsafe_allow_html=True)
            loading_placeholder.markdown(loading_html, unsafe_allow_html=True)

            request_settings = with_response_profile(
                retrieval_settings,
                active_response_mode,
                retrieval_overrides=pending_meta_current.get("retrieval_overrides"),
            )
            def set_stage(stage: str, detail: str = ""):
                status_timeline.markdown(build_status_timeline_html(stage, detail), unsafe_allow_html=True)

            load_started = time.perf_counter()
            response, citations = query_app_mode(
                prompt,
                current_mode,
                runtime_config,
                request_settings,
                response_mode=active_response_mode,
                status_cb=set_stage,
            )
            elapsed = time.perf_counter() - load_started
            min_display_seconds = loading_state.get("min_display_seconds", 0.0)
            if elapsed < min_display_seconds:
                time.sleep(min_display_seconds - elapsed)
            if queued_action == "bullets":
                response = enforce_three_bullet_response(response, citations, current_mode)
            set_stage("finalizing", "Rendering response")

            # Swap loading card for the actual response
            loading_placeholder.empty()
            status_placeholder.empty()
            status_timeline.empty()

            resp_ts = datetime.now().strftime("%b %d, %I:%M %p")
            cross = detect_cross_mode(response, current_mode) if current_mode in ("rulebook", "cba") else None
            response_msg = {
                "id": make_message_id(),
                "role": "assistant",
                "question": prompt,
                "content": response,
                "citations": citations,
                "timestamp": resp_ts,
                "cross_mode": cross,
            }
            render_assistant_message(response_msg, current_mode)

        # Store assistant message
        current_messages.append(response_msg)


if __name__ == "__main__":
    main()
