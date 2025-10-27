# 🏀 NBA Rulebook Chatbot

An AI-powered chatbot for NBA rules using Amazon Bedrock Knowledge Base and Claude.

## ✨ Features

- 🏀 **Basketball-Themed UI** - Custom orange/black NBA styling
- 🤖 **Multiple Claude Models** - Sonnet 3.5, Sonnet 3, or Haiku
- 📚 **Enhanced Citations** - Rule locations and relevance scores
- 🧠 **Smart Reasoning** - Advanced prompting for complex questions
- 📱 **Mobile Responsive** - Works on all devices
- ⚡ **Inference Profiles** - AWS's latest routing
- 🔒 **Secure** - Encrypted secrets for cloud deployment

## 🚀 Quick Deploy to Streamlit Cloud (FREE)

### 1. Push to GitHub
```bash
git init && git add . && git commit -m "NBA Rulebook Chatbot"
git remote add origin https://github.com/YOUR_USERNAME/nba-rulebook-chatbot.git
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

knowledge_base_id = "JFEGBVQF3O"
```

**Done!** Your app is live at: `https://YOUR_USERNAME-nba-rulebook-chatbot.streamlit.app`

**See DEPLOYMENT_GUIDE.md for detailed instructions**

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

**See LOCAL_TESTING.md for detailed instructions**

## 📋 Requirements

- Python 3.8+
- AWS account with Bedrock access
- Bedrock Knowledge Base ID
- IAM permissions: `bedrock:RetrieveAndGenerate`, `bedrock:Retrieve`

## 📁 Files

- `app.py` - Main application
- `requirements.txt` - Dependencies  
- `test_connection.py` - Connection test
- `setup.sh` - Setup automation
- `secrets.toml.template` - Secrets format
- `.gitignore` - Security
- `DEPLOYMENT_GUIDE.md` - Full deployment guide
- `LOCAL_TESTING.md` - Testing guide

## 💰 Cost

- **Streamlit Cloud:** FREE
- **AWS Bedrock:**
  - Claude 3 Haiku: ~$0.25/1M tokens
  - Claude 3.5 Sonnet: ~$3.00/1M tokens
- **Typical usage:** $1-10/month

## 🔒 Security

- ✅ Secrets encrypted in Streamlit Cloud
- ✅ `.gitignore` prevents committing credentials
- ✅ No credentials in code
- ✅ Supports AWS CLI or secrets file

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| "AWS credentials not found" | Add secrets in Streamlit Cloud dashboard |
| "ValidationException" | Already fixed! Uses inference profiles |
| "ResourceNotFoundException" | Check Knowledge Base ID |
| "AccessDeniedException" | Verify AWS credentials & IAM permissions |

**More help in DEPLOYMENT_GUIDE.md**

## 📚 Documentation

- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deploy to cloud
- [LOCAL_TESTING.md](LOCAL_TESTING.md) - Test locally
- [Streamlit Docs](https://docs.streamlit.io/)
- [AWS Bedrock Docs](https://docs.aws.amazon.com/bedrock/)

## 🎉 Success!

Your NBA Rulebook Chatbot is ready to deploy!

**Built with ❤️ for basketball fans** 🏀
