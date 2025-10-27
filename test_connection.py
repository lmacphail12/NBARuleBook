#!/usr/bin/env python3
"""
Test script to verify AWS Bedrock Knowledge Base connectivity
Run this before launching the Streamlit app to ensure everything is configured correctly

Supports both:
- Streamlit secrets (.streamlit/secrets.toml)
- AWS CLI credentials (~/.aws/credentials)
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import sys
import os

def load_secrets():
    """Try to load secrets from .streamlit/secrets.toml"""
    try:
        import toml
        secrets_path = os.path.join('.streamlit', 'secrets.toml')
        if os.path.exists(secrets_path):
            secrets = toml.load(secrets_path)
            return secrets
        return None
    except ImportError:
        print("ℹ️  toml package not found (not needed for AWS CLI credentials)")
        return None
    except Exception:
        return None

def get_boto_client(service_name, region='us-east-1'):
    """Get boto3 client, trying secrets first, then AWS CLI credentials"""
    secrets = load_secrets()
    
    if secrets and 'aws' in secrets:
        print("🔑 Using credentials from .streamlit/secrets.toml")
        return boto3.client(
            service_name,
            aws_access_key_id=secrets['aws']['access_key_id'],
            aws_secret_access_key=secrets['aws']['secret_access_key'],
            region_name=secrets['aws'].get('region', region)
        )
    else:
        print("🔑 Using AWS CLI credentials")
        return boto3.client(service_name, region_name=region)

def test_aws_credentials():
    """Test if AWS credentials are configured"""
    print("🔐 Testing AWS credentials...")
    try:
        sts = get_boto_client('sts')
        identity = sts.get_caller_identity()
        print(f"✅ AWS credentials valid")
        print(f"   Account: {identity['Account']}")
        print(f"   User/Role: {identity['Arn']}")
        return True
    except NoCredentialsError:
        print("❌ No AWS credentials found")
        print("   Option 1: Run 'aws configure' to set up AWS CLI credentials")
        print("   Option 2: Create .streamlit/secrets.toml with your AWS credentials")
        return False
    except Exception as e:
        print(f"❌ Error checking credentials: {str(e)}")
        return False

def test_bedrock_access(region='us-east-1'):
    """Test if Bedrock service is accessible"""
    print(f"\n🤖 Testing Bedrock access in {region}...")
    try:
        bedrock = get_boto_client('bedrock', region)
        # Try to list foundation models to verify access
        response = bedrock.list_foundation_models()
        print(f"✅ Bedrock access confirmed")
        print(f"   Available models: {len(response.get('modelSummaries', []))}")
        return True
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'AccessDeniedException':
            print("❌ Access denied to Bedrock")
            print("   Check your IAM permissions")
        else:
            print(f"❌ Error accessing Bedrock: {error_code}")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def test_knowledge_base(kb_id, region='us-east-1'):
    """Test if Knowledge Base is accessible"""
    print(f"\n📚 Testing Knowledge Base access...")
    print(f"   Knowledge Base ID: {kb_id}")
    print(f"   Region: {region}")
    
    try:
        client = get_boto_client('bedrock-agent-runtime', region)
        
        # Try a simple test query using inference profile
        response = client.retrieve_and_generate(
            input={'text': 'test'},
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': 'us.anthropic.claude-3-haiku-20240307-v1:0'  # Using inference profile
                }
            }
        )
        
        print("✅ Knowledge Base access confirmed")
        print("   Successfully retrieved and generated response")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        
        if error_code == 'ResourceNotFoundException':
            print("❌ Knowledge Base not found")
            print(f"   Verify KB ID '{kb_id}' exists in region '{region}'")
        elif error_code == 'AccessDeniedException':
            print("❌ Access denied to Knowledge Base")
            print("   Check your IAM permissions for bedrock:RetrieveAndGenerate")
        else:
            print(f"❌ Error: {error_code}")
            print(f"   Message: {error_message}")
        return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    print("=" * 60)
    print("Bedrock Knowledge Base Connectivity Test")
    print("=" * 60)
    
    # Configuration - try to load from secrets first
    secrets = load_secrets()
    if secrets and 'knowledge_base_id' in secrets:
        KB_ID = secrets['knowledge_base_id']
        print("📝 Loaded Knowledge Base ID from secrets")
    else:
        KB_ID = "JFEGBVQF3O"
    
    if secrets and 'aws' in secrets and 'region' in secrets['aws']:
        REGION = secrets['aws']['region']
        print("📝 Loaded region from secrets")
    else:
        REGION = "us-east-1"
    
    print(f"\nConfiguration:")
    print(f"  Knowledge Base ID: {KB_ID}")
    print(f"  AWS Region: {REGION}")
    print()
    
    # Run tests
    credentials_ok = test_aws_credentials()
    if not credentials_ok:
        print("\n❌ Test failed: Fix AWS credentials first")
        sys.exit(1)
    
    bedrock_ok = test_bedrock_access(REGION)
    if not bedrock_ok:
        print("\n⚠️  Bedrock access issue detected")
        print("   You may need to enable Bedrock in your AWS account")
    
    kb_ok = test_knowledge_base(KB_ID, REGION)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"AWS Credentials:  {'✅ Pass' if credentials_ok else '❌ Fail'}")
    print(f"Bedrock Access:   {'✅ Pass' if bedrock_ok else '❌ Fail'}")
    print(f"Knowledge Base:   {'✅ Pass' if kb_ok else '❌ Fail'}")
    
    if credentials_ok and bedrock_ok and kb_ok:
        print("\n🎉 All tests passed! You're ready to run the Streamlit app.")
        print("   Run: streamlit run app.py")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Please fix the issues above before running the app.")
        sys.exit(1)

if __name__ == "__main__":
    main()