#!/bin/bash

echo "🚀 Setting up Bedrock Knowledge Base Streamlit App..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "✅ Python 3 found"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed. Please install pip."
    exit 1
fi

echo "✅ pip3 found"

# Create virtual environment (optional but recommended)
echo ""
read -p "Do you want to create a virtual environment? (recommended) [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
    echo "✅ Virtual environment activated"
fi

# Install requirements
echo ""
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Check AWS credentials
echo ""
echo "🔐 Checking AWS credentials..."
if command -v aws &> /dev/null; then
    if aws sts get-caller-identity &> /dev/null; then
        echo "✅ AWS credentials configured via AWS CLI"
    else
        echo "⚠️  AWS CLI found but credentials not configured"
        echo "   Option 1: Run 'aws configure' to set up your credentials"
        echo "   Option 2: Create .streamlit/secrets.toml (see secrets.toml.template)"
    fi
else
    echo "⚠️  AWS CLI not found"
    echo "   Option 1: Install AWS CLI from https://aws.amazon.com/cli/"
    echo "   Option 2: Create .streamlit/secrets.toml with your AWS credentials"
    echo "             See secrets.toml.template for the format"
fi

echo ""
echo "✨ Setup complete!"
echo ""
echo "📝 For local development with secrets:"
echo "  1. Create directory: mkdir -p .streamlit"
echo "  2. Copy template: cp secrets.toml.template .streamlit/secrets.toml"
echo "  3. Edit .streamlit/secrets.toml with your real AWS credentials"
echo ""
echo "To run the app:"
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "  1. Make sure virtual environment is activated: source venv/bin/activate"
    echo "  2. Run: streamlit run app.py"
else
    echo "  Run: streamlit run app.py"
fi
echo ""
echo "The app will open automatically in your browser at http://localhost:8501"
echo ""