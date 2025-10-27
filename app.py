import streamlit as st
import boto3
import json
from botocore.exceptions import ClientError

# Page configuration
st.set_page_config(
    page_title="NBA Rulebook Chatbot",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for basketball-themed styling
st.markdown("""
<style>
    /* Mobile-first responsive design */
    @media only screen and (max-width: 768px) {
        .main {
            padding: 1rem !important;
        }
        
        h1 {
            font-size: 1.5rem !important;
            color: #1A1A1A !important;
            font-weight: 700 !important;
        }
        
        .subtitle {
            font-size: 0.9rem !important;
            color: #F58426 !important;
            font-weight: 600 !important;
        }
        
        /* Chat message text - CRITICAL for readability */
        .stChatMessage p {
            color: #1A1A1A !important;
            font-size: 1rem !important;
        }
        
        .stChatMessage div {
            color: #1A1A1A !important;
        }
        
        .stChatMessage {
            border-left: 4px solid #F58426 !important;
            background-color: #f8f9fa !important;
        }
        
        /* Source excerpts */
        .source-excerpt {
            padding: 0.8rem 1rem !important;
            font-size: 0.9rem !important;
            color: #1A1A1A !important;
            background: linear-gradient(135deg, #FFF8F0 0%, #FFE4D1 100%) !important;
            border-left: 3px solid #F58426 !important;
        }
        
        /* Rule location badges */
        .rule-location {
            font-size: 0.75rem !important;
            background: linear-gradient(135deg, #1A1A1A 0%, #2c2c2c 100%) !important;
            color: #F58426 !important;
            border: 2px solid #F58426 !important;
        }
        
        /* Relevance badges */
        .relevance-badge {
            background: #F58426 !important;
            color: white !important;
        }
        
        /* Metric containers */
        .metric-container {
            background: linear-gradient(135deg, #F58426 0%, #FF6B35 100%) !important;
            color: white !important;
        }
        
        .metric-container h2 {
            color: white !important;
        }
        
        .metric-container p {
            color: white !important;
        }
        
        /* Main content text */
        .main p {
            color: #1A1A1A !important;
        }
        
        /* Orange links on mobile */
        a {
            color: #F58426 !important;
        }
        
        /* Ensure all markdown text is readable */
        .stMarkdown {
            color: #1A1A1A !important;
        }
        
        /* MOBILE SCROLLING FIXES */
        
        /* Hide Streamlit footer on mobile - it blocks content */
        footer {
            display: none !important;
        }
        
        /* Make bottom toolbar less intrusive */
        .stBottom {
            background: transparent !important;
        }
        
        /* Adjust chat input container to not block content */
        .stChatInputContainer {
            position: relative !important;
            bottom: 0 !important;
            margin-bottom: 1rem !important;
            background: white !important;
            padding: 0.5rem !important;
            border-top: 1px solid #e0e0e0 !important;
        }
        
        /* Add padding to bottom of main content so chat input doesn't cover it */
        .main {
            padding-bottom: 100px !important;
        }
        
        /* Ensure scrolling works smoothly */
        .main, .stApp {
            overflow-y: auto !important;
            -webkit-overflow-scrolling: touch !important;
        }
    }
    
    /* Tablet optimization */
    @media only screen and (min-width: 769px) and (max-width: 1024px) {
        .main {
            padding: 1.5rem !important;
        }
        
        .source-excerpt {
            font-size: 0.95rem !important;
        }
        
        h1 {
            color: #1A1A1A !important;
        }
        
        .subtitle {
            color: #F58426 !important;
        }
    }
    
    /* Main app styling */
    .main {
        padding: 2rem;
        background: linear-gradient(to bottom, #f5f5f5 0%, #ffffff 100%);
        max-width: 100%;
    }
    
    /* Chat messages */
    .stChatMessage {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        border-left: 4px solid #F58426;
        max-width: 100%;
        word-wrap: break-word;
    }
    
    /* Rule location badge */
    .rule-location {
        display: inline-block;
        background: linear-gradient(135deg, #1A1A1A 0%, #2c2c2c 100%);
        color: #F58426;
        padding: 0.4rem 0.8rem;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 700;
        margin-bottom: 0.8rem;
        border: 2px solid #F58426;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* Source excerpt styling - subtle, no purple bar */
    .source-excerpt {
        background: linear-gradient(135deg, #FFF8F0 0%, #FFE4D1 100%);
        padding: 1rem 1.5rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 3px solid #F58426;
        color: #2c3e50;
        font-size: 0.95rem;
        line-height: 1.6;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        max-width: 100%;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    
    .source-excerpt:hover {
        box-shadow: 0 3px 8px rgba(245, 132, 38, 0.15);
    }
    
    /* Relevance badge */
    .relevance-badge {
        display: inline-block;
        background: #F58426;
        color: white;
        padding: 0.2rem 0.6rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    
    /* Read more button styling */
    .read-more {
        color: #F58426;
        font-weight: 600;
        font-size: 0.85rem;
        cursor: pointer;
        margin-top: 0.5rem;
    }
    
    /* Title styling - NBA colors */
    h1 {
        color: #1A1A1A;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba(245, 132, 38, 0.1);
    }
    
    /* Subtitle with basketball theme */
    .subtitle {
        color: #F58426;
        font-size: 1.1rem;
        font-weight: 600;
    }
    
    /* Info boxes */
    .stAlert {
        border-radius: 8px;
    }
    
    /* Metric styling - basketball colors */
    .metric-container {
        background: linear-gradient(135deg, #F58426 0%, #FF6B35 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
        text-align: center;
        box-shadow: 0 3px 6px rgba(0, 0, 0, 0.15);
    }
    
    /* Basketball icon animation */
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
    
    .basketball-icon {
        animation: bounce 2s ease-in-out infinite;
        display: inline-block;
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(to bottom, #1A1A1A 0%, #2c2c2c 100%);
        color: white;
    }
    
    /* Responsive images */
    img {
        max-width: 100%;
        height: auto;
    }
    
    /* Responsive containers */
    .stContainer {
        max-width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Auto-scroll to bottom on mobile after messages
st.markdown("""
<script>
    // Auto-scroll function for mobile devices
    function scrollToBottom() {
        // Check if on mobile
        if (window.innerWidth <= 768) {
            // Small delay to ensure content is rendered
            setTimeout(function() {
                window.scrollTo({
                    top: document.body.scrollHeight,
                    behavior: 'smooth'
                });
            }, 100);
        }
    }
    
    // Watch for new chat messages
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.addedNodes.length) {
                scrollToBottom();
            }
        });
    });
    
    // Start observing when page loads
    window.addEventListener('load', function() {
        const targetNode = document.querySelector('.main');
        if (targetNode) {
            observer.observe(targetNode, {
                childList: true,
                subtree: true
            });
        }
        // Initial scroll
        scrollToBottom();
    });
</script>
""", unsafe_allow_html=True)

# Initialize AWS Bedrock client
@st.cache_resource
def get_bedrock_client():
    """Initialize and cache the Bedrock Agent Runtime client
    Supports both Streamlit Cloud (secrets) and local development (AWS CLI credentials)
    """
    try:
        # Try to get credentials from Streamlit secrets first (for cloud deployment)
        if "aws" in st.secrets:
            # Verify all required keys are present
            required_keys = ["access_key_id", "secret_access_key"]
            missing_keys = [key for key in required_keys if key not in st.secrets["aws"]]
            
            if missing_keys:
                st.error(f"⚠️ Missing keys in secrets: {', '.join(missing_keys)}")
                st.info("Your secrets should have:\n```\n[aws]\naccess_key_id = \"...\"\nsecret_access_key = \"...\"\nregion = \"us-east-1\"\n```")
                return None
            
            # Credentials found and valid - create client silently
            return boto3.client(
                service_name='bedrock-agent-runtime',
                aws_access_key_id=st.secrets["aws"]["access_key_id"],
                aws_secret_access_key=st.secrets["aws"]["secret_access_key"],
                region_name=st.secrets["aws"].get("region", "us-east-1")
            )
        else:
            # No secrets found - show clear error for Streamlit Cloud
            st.error("⚠️ No AWS credentials found in secrets!")
            st.info("""
            **To fix this:**
            1. Go to your Streamlit Cloud dashboard
            2. Click the ⋮ menu on your app
            3. Click "Settings" → "Secrets"
            4. Add this format:
            
            ```toml
            [aws]
            access_key_id = "YOUR_ACCESS_KEY"
            secret_access_key = "YOUR_SECRET_KEY"
            region = "us-east-1"
            
            knowledge_base_id = "JFEGBVQF3O"
            ```
            
            5. Click "Save" and wait for app to restart
            """)
            return None
    except Exception as e:
        st.error(f"⚠️ Error initializing Bedrock client: {str(e)}")
        st.info("💡 Check that your secrets are properly formatted in Streamlit Cloud Settings → Secrets")
        return None

def query_knowledge_base(question, knowledge_base_id, model_arn):
    """Query the Bedrock Knowledge Base with enhanced reasoning and source extraction"""
    client = get_bedrock_client()
    
    if not client:
        return "Error: Could not initialize Bedrock client", []
    
    try:
        # Enhanced prompt for better reasoning about rules
        enhanced_prompt = f"""You are an expert NBA rules analyst with deep knowledge of basketball regulations. Use the rulebook sources provided to answer the following question.

Question: {question}

Instructions for your answer:
1. If the answer requires combining multiple rules, identify each relevant rule first, then explain how they connect logically
2. For "what if" or scenario questions, break down the scenario and apply the relevant rules step-by-step
3. If a direct answer isn't explicitly stated but can be logically inferred from the rules, explain your reasoning process
4. Always cite specific rules (e.g., "According to Rule 12, Section II...")
5. Be confident in logical inferences that follow from the stated rules
6. Provide clear, comprehensive explanations with your reasoning

Answer:"""

        response = client.retrieve_and_generate(
            input={
                'text': enhanced_prompt
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': knowledge_base_id,
                    'modelArn': model_arn
                }
            }
        )
        
        # Extract the generated response
        generated_text = response['output']['text']
        
        # Extract detailed source citations
        citations = []
        if 'citations' in response:
            for citation in response['citations']:
                if 'retrievedReferences' in citation:
                    for ref in citation['retrievedReferences']:
                        citation_data = {
                            'content': ref.get('content', {}).get('text', 'No content available'),
                            'uri': 'Unknown',
                            'source_type': 'Unknown',
                            'metadata': {}
                        }
                        
                        # Extract location information
                        if 'location' in ref:
                            location = ref['location']
                            
                            # S3 location
                            if 's3Location' in location:
                                s3_loc = location['s3Location']
                                citation_data['uri'] = s3_loc.get('uri', 'Unknown')
                                # Extract filename from URI
                                if citation_data['uri'] != 'Unknown':
                                    citation_data['filename'] = citation_data['uri'].split('/')[-1]
                                else:
                                    citation_data['filename'] = 'Unknown file'
                            
                            # Web location
                            elif 'webLocation' in location:
                                web_loc = location['webLocation']
                                citation_data['uri'] = web_loc.get('url', 'Unknown')
                                citation_data['source_type'] = 'Web'
                            
                            # Confluence location
                            elif 'confluenceLocation' in location:
                                confluence_loc = location['confluenceLocation']
                                citation_data['uri'] = confluence_loc.get('url', 'Unknown')
                                citation_data['source_type'] = 'Confluence'
                            
                            # Salesforce location
                            elif 'salesforceLocation' in location:
                                sf_loc = location['salesforceLocation']
                                citation_data['uri'] = sf_loc.get('url', 'Unknown')
                                citation_data['source_type'] = 'Salesforce'
                            
                            # SharePoint location
                            elif 'sharepointLocation' in location:
                                sp_loc = location['sharepointLocation']
                                citation_data['uri'] = sp_loc.get('url', 'Unknown')
                                citation_data['source_type'] = 'SharePoint'
                        
                        # Extract metadata (custom attributes)
                        if 'metadata' in ref:
                            citation_data['metadata'] = ref['metadata']
                        
                        # Extract score if available
                        if 'score' in ref:
                            citation_data['score'] = ref['score']
                        
                        citations.append(citation_data)
        
        return generated_text, citations
    
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        return f"AWS Error ({error_code}): {error_message}", []
    except Exception as e:
        return f"Error querying knowledge base: {str(e)}", []

# Main app
def main():
    st.markdown('<h1>🏀 NBA Rulebook Chatbot</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">📖 Ask questions about NBA rules and regulations</p>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Sidebar configuration
    with st.sidebar:
        st.markdown("## 🏀 Configuration")
        st.markdown("---")
        
        # Knowledge Base ID (pre-filled with user's ID, or from secrets)
        try:
            default_kb_id = st.secrets.get("knowledge_base_id", "JFEGBVQF3O")
        except:
            default_kb_id = "JFEGBVQF3O"
        
        kb_id = st.text_input(
            "📊 Knowledge Base ID",
            value=default_kb_id,
            help="Your Bedrock Knowledge Base ID"
        )
        
        # AWS Region
        region = st.selectbox(
            "🌍 AWS Region",
            ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"],
            help="Select your AWS region where your Knowledge Base is located"
        )
        
        st.success("✅ Using inference profiles")
        
        # Model selection - using inference profiles for on-demand throughput
        model_options = {
            "Claude 3.5 Sonnet v2 (Latest)": f"us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            "Claude 3.5 Sonnet v1": f"us.anthropic.claude-3-5-sonnet-20240620-v1:0",
            "Claude 3 Sonnet": f"us.anthropic.claude-3-sonnet-20240229-v1:0",
            "Claude 3 Haiku": f"us.anthropic.claude-3-haiku-20240307-v1:0"
        }
        
        model_display = st.selectbox(
            "🤖 Claude Model",
            list(model_options.keys()),
            help="Select the Claude model to use"
        )
        
        # Use inference profile ID instead of model ARN
        model_arn = model_options[model_display]
        
        st.markdown("---")
        
        # Session statistics
        st.markdown("### 📊 Game Stats")
        
        message_count = len([m for m in st.session_state.get('messages', []) if m['role'] == 'user'])
        st.markdown(f"""
        <div class="metric-container">
            <h2 style="margin: 0; font-size: 2rem;">🏀 {message_count}</h2>
            <p style="margin: 0; opacity: 0.9;">Questions Asked</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        st.markdown("### 💡 Tips")
        st.markdown("""
        - Ask about specific rules
        - Reference rule sections or numbers
        - Ask for clarifications
        - Compare different scenarios
        """)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.messages = []
                st.rerun()
        with col2:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Show welcome screen if no messages
    if len(st.session_state.messages) == 0:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
            <div style="text-align: center; padding: 2rem;">
                <h2 style="color: #F58426;">🏀 Welcome to the NBA Rulebook Chatbot!</h2>
                <p style="font-size: 1.1rem; color: #666;">
                    Ask me anything about NBA rules, regulations, and gameplay. I'll provide answers based on the official rulebook.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### 🎯 Example Questions:")
            
            example_col1, example_col2 = st.columns(2)
            
            with example_col1:
                st.info("🏀 What constitutes a traveling violation?")
                st.info("⏱️ How long is a shot clock in the NBA?")
            
            with example_col2:
                st.info("🤚 What are the rules for goaltending?")
                st.info("⚖️ What's the difference between a foul and a violation?")
            
            st.markdown("---")
            st.markdown("**💡 Tip:** Type your question in the chat box below to get started!")
    
    # Display chat messages
    else:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                # Display enhanced citations if available
                if message["role"] == "assistant" and "citations" in message and message["citations"]:
                    st.markdown("---")
                    st.markdown("### 📚 Sources from Rulebook")
                    
                    for i, citation in enumerate(message["citations"], 1):
                        # Get content
                        content = citation.get('content', 'No content available')
                        metadata = citation.get('metadata', {})
                        
                        # Extract rule location from metadata
                        rule_location = None
                        location_parts = []
                        
                        # Common metadata keys for rule location
                        if 'rule' in metadata:
                            location_parts.append(f"Rule {metadata['rule']}")
                        if 'section' in metadata:
                            location_parts.append(f"Section {metadata['section']}")
                        if 'part' in metadata or 'subsection' in metadata:
                            part = metadata.get('part', metadata.get('subsection'))
                            location_parts.append(f"Part {part}")
                        if 'article' in metadata:
                            location_parts.append(f"Article {metadata['article']}")
                        if 'page' in metadata:
                            location_parts.append(f"Page {metadata['page']}")
                        
                        if location_parts:
                            rule_location = ", ".join(location_parts)
                        
                        # Show rule location badge if available
                        if rule_location:
                            st.markdown(f'<div class="rule-location">📍 {rule_location}</div>', unsafe_allow_html=True)
                        
                        # Show relevance score if available
                        if 'score' in citation:
                            score_pct = citation['score'] * 100
                            st.markdown(f'<span class="relevance-badge">Relevance: {score_pct:.1f}%</span>', unsafe_allow_html=True)
                        
                        # Show preview (first 200 chars)
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
    if prompt := st.chat_input("Ask a question about NBA rules and regulations..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get response from knowledge base
        with st.chat_message("assistant"):
            with st.spinner("🏀 Searching the rulebook..."):
                response, citations = query_knowledge_base(prompt, kb_id, model_arn)
            
            st.markdown(response)
            
            # Display enhanced citations
            if citations:
                st.markdown("---")
                st.markdown("### 📚 Sources from Rulebook")
                
                for i, citation in enumerate(citations, 1):
                    # Get content
                    content = citation.get('content', 'No content available')
                    metadata = citation.get('metadata', {})
                    
                    # Extract rule location from metadata
                    rule_location = None
                    location_parts = []
                    
                    # Common metadata keys for rule location
                    if 'rule' in metadata:
                        location_parts.append(f"Rule {metadata['rule']}")
                    if 'section' in metadata:
                        location_parts.append(f"Section {metadata['section']}")
                    if 'part' in metadata or 'subsection' in metadata:
                        part = metadata.get('part', metadata.get('subsection'))
                        location_parts.append(f"Part {part}")
                    if 'article' in metadata:
                        location_parts.append(f"Article {metadata['article']}")
                    if 'page' in metadata:
                        location_parts.append(f"Page {metadata['page']}")
                    
                    if location_parts:
                        rule_location = ", ".join(location_parts)
                    
                    # Show rule location badge if available
                    if rule_location:
                        st.markdown(f'<div class="rule-location">📍 {rule_location}</div>', unsafe_allow_html=True)
                    
                    # Show relevance score if available
                    if 'score' in citation:
                        score_pct = citation['score'] * 100
                        st.markdown(f'<span class="relevance-badge">Relevance: {score_pct:.1f}%</span>', unsafe_allow_html=True)
                    
                    # Show preview (first 200 chars)
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
        
        # Add assistant response to chat history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "citations": citations
        })

if __name__ == "__main__":
    main()