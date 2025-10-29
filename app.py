import streamlit as st
import boto3
import json
import uuid
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(
    page_title="NBA Assistant - Rulebook & CBA",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed" 
)

# Theme configurations
THEMES = {
    "rulebook": {
        "name": "🏀 NBA Rulebook",
        "kb_id": "JFEGBVQF3O",
        "primary_color": "#F58426",  # Orange
        "secondary_color": "#1A1A1A",  # Black
        "gradient_start": "#F58426",
        "gradient_end": "#FF6B35",
        "title": "🏀 NBA Rulebook Chatbot",
        "subtitle": "📖 Ask questions about NBA rules and regulations",
        "icon": "🏀",
        "examples": [
            "What constitutes a traveling violation?",
            "How long is a shot clock in the NBA?",
            "What are the rules for goaltending?",
            "What's the difference between a foul and a violation?"
        ]
    },
    "cba": {
        "name": "💰 CBA & Salary Cap",
        "kb_id": "B902HDGE8W",
        "primary_color": "#2E7D32",  # Money Green
        "secondary_color": "#FFD700",  # Gold
        "gradient_start": "#2E7D32",
        "gradient_end": "#4CAF50",
        "title": "💰 NBA CBA & Salary Cap Assistant",
        "subtitle": "💵 Ask questions about contracts, salary cap, and league rules",
        "icon": "💰",
        "examples": [
            "What's a restricted free agent?",
            "What rules are there around team options?",
            "When can teams claim a waived player?",
            "How does the salary cap work?"
        ]
    }
}

# Initialize session state for mode
if "mode" not in st.session_state:
    st.session_state.mode = "rulebook"
if "messages" not in st.session_state:
    st.session_state.messages = []
# Initialize session IDs for conversation memory (one per mode)
if "session_ids" not in st.session_state:
    st.session_state.session_ids = {
        "rulebook": None,
        "cba": None
    }

# Get current theme
theme = THEMES[st.session_state.mode]

# Dynamic CSS based on theme
st.markdown(f"""
<style>
    /* Mobile-first responsive design */
    @media only screen and (max-width: 768px) {{
        .main {{
            padding: 1rem !important;
            padding-bottom: 100px !important;
        }}
        
        h1 {{
            font-size: 1.5rem !important;
            color: #1A1A1A !important;
            font-weight: 700 !important;
        }}
        
        .subtitle {{
            font-size: 0.9rem !important;
            color: {theme['primary_color']} !important;
            font-weight: 600 !important;
        }}
        
        /* Chat message text - CRITICAL for readability */
        .stChatMessage p {{
            color: #1A1A1A !important;
            font-size: 1rem !important;
        }}
        
        .stChatMessage div {{
            color: #1A1A1A !important;
        }}
        
        .stChatMessage {{
            border-left: 4px solid {theme['primary_color']} !important;
            background-color: #f8f9fa !important;
        }}
        
        /* Source excerpts */
        .source-excerpt {{
            padding: 0.8rem 1rem !important;
            font-size: 0.9rem !important;
            color: #1A1A1A !important;
            background: linear-gradient(135deg, #FFF8F0 0%, #FFE4D1 100%) !important;
            border-left: 3px solid {theme['primary_color']} !important;
        }}
        
        /* Rule/CBA location badges */
        .rule-location {{
            font-size: 0.75rem !important;
            background: linear-gradient(135deg, {theme['secondary_color']} 0%, {theme['primary_color']} 100%) !important;
            color: white !important;
            border: 2px solid {theme['primary_color']} !important;
        }}
        
        /* Relevance badges */
        .relevance-badge {{
            background: {theme['primary_color']} !important;
            color: white !important;
        }}
        
        /* Metric containers */
        .metric-container {{
            background: linear-gradient(135deg, {theme['gradient_start']} 0%, {theme['gradient_end']} 100%) !important;
            color: white !important;
        }}
        
        .metric-container h2 {{
            color: white !important;
        }}
        
        .metric-container p {{
            color: white !important;
        }}
        
        /* Main content text */
        .main p {{
            color: #1A1A1A !important;
        }}
        
        /* Links */
        a {{
            color: {theme['primary_color']} !important;
        }}
        
        /* Ensure all markdown text is readable */
        .stMarkdown {{
            color: #1A1A1A !important;
        }}
        
        /* MOBILE SCROLLING FIXES */
        footer {{
            display: none !important;
        }}
        
        .stBottom {{
            background: transparent !important;
        }}
        
        /* Chat input styling */
        .stChatInputContainer {{
            position: relative !important;
            bottom: 0 !important;
            margin-bottom: 1rem !important;
            background: white !important;
            padding: 0.5rem !important;
            border-top: 1px solid #e0e0e0 !important;
        }}
        
        .stChatInputContainer textarea {{
            color: #1A1A1A !important;
            font-size: 1rem !important;
            background-color: white !important;
        }}
        
        .stChatInputContainer input {{
            color: #1A1A1A !important;
            font-size: 1rem !important;
            background-color: white !important;
        }}
        
        .stChatInputContainer textarea::placeholder,
        .stChatInputContainer input::placeholder {{
            color: #666666 !important;
            opacity: 0.7 !important;
        }}
        
        .stChatInputContainer button {{
            background-color: {theme['primary_color']} !important;
            color: white !important;
        }}
        
        /* Ensure scrolling works smoothly */
        .main, .stApp {{
            overflow-y: auto !important;
            -webkit-overflow-scrolling: touch !important;
        }}
    }}
    
    /* Tablet optimization */
    @media only screen and (min-width: 769px) and (max-width: 1024px) {{
        .main {{
            padding: 1.5rem !important;
        }}
        
        h1 {{
            color: #1A1A1A !important;
        }}
        
        .subtitle {{
            color: {theme['primary_color']} !important;
        }}
    }}
    
    /* Main app styling */
    .main {{
        padding: 2rem;
        background: linear-gradient(to bottom, #f5f5f5 0%, #ffffff 100%);
        max-width: 100%;
    }}
    
    /* Chat messages */
    .stChatMessage {{
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        border-left: 4px solid {theme['primary_color']};
        max-width: 100%;
        word-wrap: break-word;
    }}
    
    /* Location badges (rules or CBA sections) */
    .rule-location {{
        display: inline-block;
        background: linear-gradient(135deg, {theme['secondary_color']} 0%, {theme['primary_color']} 100%);
        color: white;
        padding: 0.4rem 0.8rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 700;
        margin-bottom: 0.8rem;
        border: 2px solid {theme['primary_color']};
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    
    /* Source excerpt styling */
    .source-excerpt {{
        background: linear-gradient(135deg, #FFF8F0 0%, #FFE4D1 100%);
        padding: 1rem 1.5rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 3px solid {theme['primary_color']};
        color: #2c3e50;
        font-size: 0.95rem;
        line-height: 1.6;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        max-width: 100%;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }}
    
    .source-excerpt:hover {{
        box-shadow: 0 3px 8px rgba({theme['primary_color']}, 0.15);
    }}
    
    /* Relevance badge */
    .relevance-badge {{
        display: inline-block;
        background: {theme['primary_color']};
        color: white;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }}
    
    /* Title styling */
    h1 {{
        color: #1A1A1A;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba({theme['primary_color']}, 0.1);
    }}
    
    /* Subtitle */
    .subtitle {{
        color: {theme['primary_color']};
        font-size: 1.1rem;
        font-weight: 600;
    }}
    
    /* Info boxes */
    .stAlert {{
        border-radius: 8px;
    }}
    
    /* Metric styling */
    .metric-container {{
        background: linear-gradient(135deg, {theme['gradient_start']} 0%, {theme['gradient_end']} 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
        text-align: center;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.15);
    }}
    
    /* Mode toggle buttons */
    .stRadio > div {{
        flex-direction: row !important;
        gap: 1rem;
        justify-content: center;
        margin-bottom: 2rem;
    }}
    
    .stRadio > div > label {{
        background: white;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        border: 2px solid #e0e0e0;
        cursor: pointer;
        transition: all 0.3s ease;
        font-weight: 600;
        font-size: 1.1rem;
    }}
    
    .stRadio > div > label:hover {{
        border-color: {theme['primary_color']};
        background: #f8f9fa;
    }}
    
    .stRadio > div > label[data-baseweb="radio"] > div:first-child {{
        display: none;
    }}
    
    /* Responsive images */
    img {{
        max-width: 100%;
        height: auto;
    }}
    
    /* Responsive containers */
    .stContainer {{
        max-width: 100%;
    }}
</style>
""", unsafe_allow_html=True)

# Auto-scroll JavaScript for mobile
st.markdown("""
<script>
    function scrollToBottom() {
        if (window.innerWidth <= 768) {
            setTimeout(function() {
                window.scrollTo({
                    top: document.body.scrollHeight,
                    behavior: 'smooth'
                });
            }, 100);
        }
    }
    
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length) {
                scrollToBottom();
            }
        });
    });
    
    window.addEventListener('load', function() {
        const targetNode = document.querySelector('.main');
        if (targetNode) {
            observer.observe(targetNode, {
                childList: true,
                subtree: true
            });
        }
        scrollToBottom();
    });
</script>
""", unsafe_allow_html=True)

# Initialize AWS Bedrock client
@st.cache_resource
def get_bedrock_client():
    """Initialize and cache the Bedrock Agent Runtime client"""
    try:
        if "aws" in st.secrets:
            required_keys = ["access_key_id", "secret_access_key"]
            missing_keys = [key for key in required_keys if key not in st.secrets["aws"]]
            
            if missing_keys:
                st.error(f"⚠️ Missing keys in secrets: {', '.join(missing_keys)}")
                return None
            
            return boto3.client(
                service_name='bedrock-agent-runtime',
                aws_access_key_id=st.secrets["aws"]["access_key_id"],
                aws_secret_access_key=st.secrets["aws"]["secret_access_key"],
                region_name=st.secrets["aws"].get("region", "us-east-1")
            )
        else:
            st.error("⚠️ No AWS credentials found in secrets!")
            st.info("""
            **To fix this:**
            1. Go to Streamlit Cloud dashboard
            2. Click Settings → Secrets
            3. Add your AWS credentials
            """)
            return None
    except Exception as e:
        st.error(f"⚠️ Error initializing Bedrock client: {str(e)}")
        return None

def query_knowledge_base(question, knowledge_base_id, model_arn, mode="rulebook", session_id=None):
    """Query the Bedrock Knowledge Base with conversation memory support"""
    client = get_bedrock_client()
    
    if not client:
        return "Error: Could not initialize Bedrock client", [], None
    
    # Generate a new session ID if none provided
    if session_id is None:
        session_id = str(uuid.uuid4())
    
    try:
        # Enhanced prompt based on mode
        if mode == "rulebook":
            enhanced_prompt = f"""You are an expert NBA rules analyst with deep knowledge of basketball regulations. Use the rulebook sources provided to answer the following question.

Question: {question}

Instructions for your answer:
1. If the answer requires combining multiple rules, identify each relevant rule first, then explain how they connect logically
2. For "what if" or scenario questions, break down the scenario and apply the relevant rules step-by-step
3. If a direct answer isn't explicitly stated but can be logically inferred from the rules, explain your reasoning process
4. Always cite specific rules (e.g., "According to Rule 12, Section II...")
5. Be confident in logical inferences that follow from the stated rules
6. Provide clear, comprehensive explanations with your reasoning
7. Remember the context of our conversation - if this is a follow-up question, reference what we previously discussed

Answer:"""
        else:  # CBA mode
            enhanced_prompt = f"""You are an expert on the NBA Collective Bargaining Agreement (CBA) with deep knowledge of salary cap rules, contract structures, and league regulations. Use the CBA sources provided to answer the following question.

Question: {question}

Instructions for your answer:
1. If the answer involves multiple CBA articles or salary cap rules, explain how they work together
2. For questions about contracts or cap situations, break down the calculation or process step-by-step
3. Always cite specific CBA articles or sections when available
4. Explain complex financial terms in clear language
5. If discussing salary cap implications, include relevant numbers or percentages when applicable
6. Provide practical examples when helpful
7. Remember the context of our conversation - if this is a follow-up question, reference what we previously discussed

Answer:"""

        # Build the API request with sessionId for conversation memory
        request_params = {
            'input': {
                'text': enhanced_prompt
            },
            'retrieveAndGenerateConfiguration': {
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': knowledge_base_id,
                    'modelArn': model_arn
                }
            }
        }
        
        # Add sessionId to maintain conversation context
        if session_id:
            request_params['sessionId'] = session_id
        
        response = client.retrieve_and_generate(**request_params)
        
        # Get the session ID from response (will be the same or newly generated)
        returned_session_id = response.get('sessionId', session_id)
        
        # Extract the generated response
        generated_text = response['output']['text']
        
        # Extract detailed source citations
        citations = []
        if 'citations' in response:
            for citation in response['citations']:
                if 'retrievedReferences' in citation:
                    for ref in citation['retrievedReferences']:
                        content = ref.get('content', {}).get('text', 'No content available')
                        location = ref.get('location', {})
                        s3_location = location.get('s3Location', {})
                        
                        citation_data = {
                            'content': content,
                            'uri': s3_location.get('uri', 'Unknown source'),
                            'score': ref.get('metadata', {}).get('score', 0),
                            'metadata': ref.get('metadata', {})
                        }
                        citations.append(citation_data)
        
        return generated_text, citations, returned_session_id
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        return f"AWS Error ({error_code}): {error_message}", [], session_id
    except Exception as e:
        return f"Error querying knowledge base: {str(e)}", [], session_id

# Main app
def main():
    # Mode selector at the top
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        selected_mode = st.radio(
            "",
            options=["rulebook", "cba"],
            format_func=lambda x: THEMES[x]["name"],
            horizontal=True,
            label_visibility="collapsed"
        )
        
        # Clear messages if mode changes
        if selected_mode != st.session_state.mode:
            st.session_state.mode = selected_mode
            st.session_state.messages = []
            st.rerun()
    
    # Get current theme
    theme = THEMES[st.session_state.mode]
    
    # Title and subtitle
    st.markdown(f'<h1>{theme["title"]}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="subtitle">{theme["subtitle"]}</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar configuration
    with st.sidebar:
        st.markdown(f"## {theme['icon']} Configuration")
        st.markdown("---")
        
        # Knowledge Base ID (pre-filled based on mode)
        kb_id = st.text_input(
            "📊 Knowledge Base ID",
            value=theme["kb_id"],
            help="Your Bedrock Knowledge Base ID"
        )
        
        # Model selection
        st.subheader("Model Settings")
        model_options = {
            "Claude Sonnet 4.5 ⭐ (Best)": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "Claude Opus 4.1 (Most Powerful)": "us.anthropic.claude-opus-4-1-20250805-v1:0",
            "Claude Sonnet 4": "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "Claude Haiku 4.5 (Fastest)": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
            "Claude 3 Opus": "us.anthropic.claude-3-opus-20240229-v1:0",
            "Claude 3.5 Sonnet v2": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "Claude 3.5 Sonnet v1": "us.anthropic.claude-3-5-sonnet-20240620-v1:0",
            "Claude 3 Sonnet": "us.anthropic.claude-3-sonnet-20240229-v1:0",
            "Claude 3 Haiku": "us.anthropic.claude-3-haiku-20240307-v1:0"
        }
        
        # Set default based on mode
        default_model = "Claude Sonnet 4.5 ⭐ (Best)" if st.session_state.mode == "cba" else "Claude Haiku 4.5 (Fastest)"
        default_index = list(model_options.keys()).index(default_model)
        
        model_display = st.selectbox(
            "🤖 Claude Model",
            list(model_options.keys()),
            index=default_index,
            help="Select the Claude model to use. Claude 4 models offer the best performance!"
        )
        
        model_arn = model_options[model_display]
        
        st.markdown("---")
        
        # Session statistics
        st.markdown("### 📊 Stats")
        
        message_count = len([m for m in st.session_state.messages if m['role'] == 'user'])
        st.markdown(f"""
        <div class="metric-container">
            <h2 style="margin: 0; font-size: 2rem;">{theme['icon']} {message_count}</h2>
            <p style="margin: 0; opacity: 0.9;">Questions Asked</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        st.markdown("### 💡 Tips")
        if st.session_state.mode == "rulebook":
            st.markdown("""
            - Ask about specific rules
            - Reference rule sections or numbers
            - Ask for clarifications
            - Compare different scenarios
            """)
        else:  # CBA mode
            st.markdown("""
            - Ask about salary cap rules
            - Contract structures and types
            - Free agency regulations
            - Trade and roster rules
            """)
        
        st.markdown("---")
        
        st.markdown("### 🤖 Model Guide")
        st.markdown("""
        **Claude 4 Models (Newest!):**
        - **Sonnet 4.5** ⭐ - Best overall
        - **Opus 4.1** - Most powerful
        - **Haiku 4.5** - Fastest & cheap
        
        **When to use what:**
        - Complex questions → Sonnet 4.5
        - Simple lookups → Haiku 4.5
        - Edge cases → Opus 4.1
        """)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.messages = []
                # Reset session ID for current mode to start fresh conversation
                st.session_state.session_ids[st.session_state.mode] = None
                st.rerun()
        with col2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
    
    # Show welcome screen if no messages
    if len(st.session_state.messages) == 0:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"""
            <div style="text-align: center; padding: 2rem;">
                <h2 style="color: {theme['primary_color']};">{theme['icon']} Welcome!</h2>
                <p style="font-size: 1.1rem; color: #666;">
                    {"Ask me anything about NBA rules, regulations, and gameplay." if st.session_state.mode == "rulebook" 
                     else "Ask me about NBA contracts, salary cap, and league business rules."}
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### 🎯 Example Questions:")
            
            example_col1, example_col2 = st.columns(2)
            
            for i, example in enumerate(theme["examples"]):
                with example_col1 if i % 2 == 0 else example_col2:
                    st.info(f"{theme['icon']} {example}")
            
            st.markdown("---")
            st.markdown("**💡 Tip:** Type your question in the chat box below to get started!")
    
    # Display chat messages
    else:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                # Display citations if available
                if message["role"] == "assistant" and "citations" in message and message["citations"]:
                    st.markdown("---")
                    st.markdown(f"### 📚 Sources from {theme['name'].split()[1]}")
                    
                    for i, citation in enumerate(message["citations"], 1):
                        content = citation.get('content', 'No content available')
                        metadata = citation.get('metadata', {})
                        
                        # Extract location from metadata
                        rule_location = None
                        location_parts = []
                        
                        # Common metadata keys
                        for key in ['rule', 'section', 'article', 'part', 'subsection', 'page']:
                            if key in metadata:
                                location_parts.append(f"{key.title()} {metadata[key]}")
                        
                        if location_parts:
                            rule_location = ", ".join(location_parts)
                        
                        # Show location badge if available
                        if rule_location:
                            st.markdown(f'<div class="rule-location">📍 {rule_location}</div>', unsafe_allow_html=True)
                        
                        # Show relevance score if available
                        if 'score' in citation:
                            score_pct = citation['score'] * 100
                            st.markdown(f'<span class="relevance-badge">Relevance: {score_pct:.1f}%</span>', unsafe_allow_html=True)
                        
                        # Show preview
                        preview = content[:200] + "..." if len(content) > 200 else content
                        
                        st.markdown(f"""
                        <div class="source-excerpt">
                            {preview}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Add expander for full text if content is long
                        if len(content) > 200:
                            with st.expander("📖 Read full excerpt"):
                                st.markdown(f"_{content}_")
                        
                        st.markdown("")  # Spacing
    
    # Chat input
    placeholder_text = "Ask a question about NBA rules..." if st.session_state.mode == "rulebook" else "Ask about contracts, salary cap, or CBA rules..."
    
    if prompt := st.chat_input(placeholder_text):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get response from knowledge base
        with st.chat_message("assistant"):
            with st.spinner(f"{theme['icon']} Searching..."):
                # Get the current session ID for this mode
                current_session_id = st.session_state.session_ids.get(st.session_state.mode)
                
                # Query with conversation memory
                response, citations, new_session_id = query_knowledge_base(
                    prompt, 
                    kb_id, 
                    model_arn, 
                    st.session_state.mode,
                    session_id=current_session_id
                )
                
                # Store the session ID for future queries in this mode
                st.session_state.session_ids[st.session_state.mode] = new_session_id
            
            st.markdown(response)
            
            # Display citations
            if citations:
                st.markdown("---")
                st.markdown(f"### 📚 Sources from {theme['name'].split()[1]}")
                
                for i, citation in enumerate(citations, 1):
                    content = citation.get('content', 'No content available')
                    metadata = citation.get('metadata', {})
                    
                    # Extract location from metadata
                    rule_location = None
                    location_parts = []
                    
                    for key in ['rule', 'section', 'article', 'part', 'subsection', 'page']:
                        if key in metadata:
                            location_parts.append(f"{key.title()} {metadata[key]}")
                    
                    if location_parts:
                        rule_location = ", ".join(location_parts)
                    
                    if rule_location:
                        st.markdown(f'<div class="rule-location">📍 {rule_location}</div>', unsafe_allow_html=True)
                    
                    if 'score' in citation:
                        score_pct = citation['score'] * 100
                        st.markdown(f'<span class="relevance-badge">Relevance: {score_pct:.1f}%</span>', unsafe_allow_html=True)
                    
                    preview = content[:200] + "..." if len(content) > 200 else content
                    
                    st.markdown(f"""
                    <div class="source-excerpt">
                        {preview}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if len(content) > 200:
                        with st.expander("📖 Read full excerpt"):
                            st.markdown(f"_{content}_")
                    
                    st.markdown("")
        
        # Add assistant response to chat history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "citations": citations
        })

if __name__ == "__main__":
    main()