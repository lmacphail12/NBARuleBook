# 🏀 NBA Assistant - Rulebook & CBA Chatbot

An AI-powered dual-mode chatbot for NBA rules and salary cap/CBA using Amazon Bedrock Knowledge Base and Claude.

## ✨ Features

- 🔄 **Dual Mode System** - Switch between Rulebook and CBA/Salary Cap modes
- 🏀 **NBA Rulebook Mode** - Ask about game rules, violations, and regulations
- 💰 **CBA & Salary Cap Mode** - Ask about contracts, cap rules, and league business
- 🎨 **Themed UI** - Dynamic orange/black for Rulebook, green/gold for CBA
- 🤖 **Multiple Claude Models** - Sonnet 3.5 v2, Sonnet 3.5 v1, Sonnet 3, or Haiku
- 📚 **Enhanced Citations** - Rule/section locations and relevance scores
- 🧠 **Smart Reasoning** - Advanced prompting for complex questions
- 📱 **Mobile Responsive** - Optimized for all devices with smooth scrolling
- ⚡ **Inference Profiles** - AWS's latest routing technology
- 🔒 **Secure** - Encrypted secrets for cloud deployment

## 🎯 What You Can Ask

### 🏀 Rulebook Mode
- "What constitutes a traveling violation?"
- "How long is a shot clock in the NBA?"
- "What are the rules for goaltending?"
- "What's the difference between a foul and a violation?"

### 💰 CBA & Salary Cap Mode
- "What's a restricted free agent?"
- "What rules are there around team options?"
- "When can teams claim a waived player?"
- "How does the salary cap work?"

## 🚀 Quick Deploy to Streamlit Cloud (FREE)

### 1. Push to GitHub
```bash
git init && git add . && git commit -m "NBA Assistant App"
git remote add origin https://github.com/YOUR_USERNAME/nba-assistant.git
git push -u origin main
```

### 2. Deploy on Streamlit Cloud
- Go to https://share.streamlit.io/
- Sign in with GitHub  
- Click "New app" → Select your repo → Deploy

### 3. Add Secrets
In Streamlit Cloud (Settings → Secrets):
```toml
[aws]
access_key_id = "YOUR_AWS_ACCESS_KEY_ID"
secret_access_key = "YOUR_AWS_SECRET_ACCESS_KEY"
region = "us-east-1"

# Knowledge Base IDs (both modes)
knowledge_base_id = "JFEGBVQF3O"  # Rulebook KB
cba_knowledge_base_id = "B902HDGE8W"  # CBA KB
```

**Done!** Your app is live at: `https://YOUR_USERNAME-nba-assistant.streamlit.app`

## 🧪 Run Locally

### Quick Start
```bash
pip install -r requirements.txt
aws configure
python test_connection.py
streamlit run app.py
```

### With Secrets File
```bash
mkdir -p .streamlit
cp secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your credentials
streamlit run app.py
```

## 📋 Requirements

- Python 3.8+
- AWS account with Bedrock access
- Two Bedrock Knowledge Base IDs (Rulebook + CBA)
- IAM permissions: `bedrock:RetrieveAndGenerate`, `bedrock:Retrieve`

## 🗂️ Knowledge Base Configuration

The app uses two separate Knowledge Bases:

| Mode | Knowledge Base ID | Content |
|------|-------------------|---------|
| 🏀 Rulebook | `JFEGBVQF3O` | NBA game rules and regulations |
| 💰 CBA | `B902HDGE8W` | Salary cap, contracts, CBA rules |

Users can switch modes using the toggle at the top of the app!

## 📁 Files

- `app.py` - Main application with dual-mode support
- `requirements.txt` - Dependencies  
- `test_connection.py` - Connection test for both KBs
- `setup.sh` - Setup automation
- `secrets.toml.template` - Secrets format
- `.gitignore` - Security

## 🎨 Theme System

Each mode has its own custom theme:

**🏀 Rulebook Mode:**
- Colors: Basketball orange (#F58426) and black
- Focus: Game rules, violations, regulations

**💰 CBA Mode:**
- Colors: Money green (#2E7D32) and gold
- Focus: Salary cap, contracts, free agency

## 💰 Cost

- **Streamlit Cloud:** FREE
- **AWS Bedrock:**
  - Claude 3 Haiku: ~$0.25/1M tokens
  - Claude 3.5 Sonnet: ~$3.00/1M tokens
  - Claude 3.5 Sonnet v2: ~$3.00/1M tokens
- **Typical usage:** $1-10/month

## 🤖 Available Models

The app supports multiple Claude models via AWS inference profiles:

- **Claude 3.5 Sonnet v2** (Latest & Best) - `us.anthropic.claude-3-5-sonnet-20241022-v2:0`
- **Claude 3.5 Sonnet v1** - `us.anthropic.claude-3-5-sonnet-20240620-v1:0`
- **Claude 3 Sonnet** - `us.anthropic.claude-3-sonnet-20240229-v1:0`
- **Claude 3 Haiku** (Fastest & Cheapest) - `us.anthropic.claude-3-haiku-20240307-v1:0`

## 🔒 Security

- ✅ Secrets encrypted in Streamlit Cloud
- ✅ `.gitignore` prevents committing credentials
- ✅ No credentials in code
- ✅ Supports AWS CLI or secrets file
- ✅ Separate Knowledge Bases for data isolation

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| "AWS credentials not found" | Add secrets in Streamlit Cloud dashboard |
| "ValidationException" | Already fixed! Uses inference profiles |
| "ResourceNotFoundException" | Check Knowledge Base ID for current mode |
| "AccessDeniedException" | Verify AWS credentials & IAM permissions |
| Mode switch not working | Clear browser cache and refresh |
| Citations not showing | Check metadata in Knowledge Base |

## 📊 Features Breakdown

### Dual Mode System
- Toggle between Rulebook and CBA at the top
- Independent chat histories per mode
- Mode-specific example questions
- Dynamic theming based on mode

### Enhanced Citations
- Source excerpts with relevance scores
- Rule/section/article location badges
- Full text expanders for long excerpts
- Metadata-driven source attribution

### Mobile Optimization
- Touch-friendly interface
- Smooth scrolling on iOS and Android
- Responsive chat input
- Optimized text readability

## 🚀 Getting Started

1. **Deploy to Streamlit Cloud** (easiest)
2. **Add your AWS credentials** in Streamlit secrets
3. **Toggle between modes** to explore both features
4. **Ask questions** about NBA rules or CBA/salary cap
5. **Review citations** to see source material

## 📚 Documentation

- [Streamlit Docs](https://docs.streamlit.io/)
- [AWS Bedrock Docs](https://docs.aws.amazon.com/bedrock/)
- [Claude Models](https://www.anthropic.com/claude)

## 🎉 Success!

Your NBA Assistant is ready to answer questions about both game rules and league business!

**Built with ❤️ for basketball fans and NBA enthusiasts** 🏀💰
