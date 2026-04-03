#!/usr/bin/env python3
"""
Setup script for opportunity scraper environment variables
"""

import os
from pathlib import Path

def setup_environment():
    """Interactive setup for environment variables"""
    
    print("🔧 Opportunity Scraper Environment Setup")
    print("=" * 50)
    
    # Check if .env file exists
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        print("⚠️  .env file already exists")
        overwrite = input("Do you want to overwrite it? (y/N): ").lower()
        if overwrite != 'y':
            print("Setup cancelled. Existing .env file preserved.")
            return
    
    print("\nPlease enter your environment variables:")
    print("(Press Enter to skip any field)")
    
    # Get user input
    monday_key = input("MONDAY_API_KEY: ").strip()
    monday_board_id = input("MONDAY_BOARD_ID: ").strip()
    sam_api_key = input("SAM_API_KEY (for SAM.gov scrapers): ").strip()
    slack_token = input("SLACK_BOT_TOKEN: ").strip()
    slack_channel = input("SLACK_CHANNEL (default opportunities channel): ").strip()
    cuas_slack_channel = input("CUAS_SLACK_CHANNEL (CUAS-specific channel): ").strip()
    
    # Create .env file
    env_content = """# Opportunity Scraper Environment Variables
# Generated automatically by setup_env.py

"""
    
    if monday_key:
        env_content += f"MONDAY_API_KEY={monday_key}\n"
    else:
        env_content += "# MONDAY_API_KEY=your_monday_api_key_here\n"
    
    if monday_board_id:
        env_content += f"MONDAY_BOARD_ID={monday_board_id}\n"
    else:
        env_content += "# MONDAY_BOARD_ID=your_board_id_here\n"
    
    if sam_api_key:
        env_content += f"SAM_API_KEY={sam_api_key}\n"
    else:
        env_content += "# SAM_API_KEY=your_sam_api_key_here\n"
    
    if slack_token:
        env_content += f"SLACK_BOT_TOKEN={slack_token}\n"
    else:
        env_content += "# SLACK_BOT_TOKEN=your_slack_bot_token_here\n"
    
    if slack_channel:
        env_content += f"SLACK_CHANNEL={slack_channel}\n"
    else:
        env_content += "# SLACK_CHANNEL=your_slack_channel_id_here\n"
    
    # CUAS-specific channel
    if cuas_slack_channel:
        env_content += f"\n# CUAS-specific Slack channel\nCUAS_SLACK_CHANNEL={cuas_slack_channel}\n"
    else:
        env_content += "\n# CUAS-specific Slack channel\n# CUAS_SLACK_CHANNEL=your_cuas_slack_channel_id_here\n"
    
    # Write to .env file
    with open(env_file, 'w') as f:
        f.write(env_content)
    
    print(f"\n✅ Environment variables saved to: {env_file}")
    print("\nTo apply changes:")
    print("1. Restart the master scheduler")
    print("2. Or run: source ~/.zshrc")
    
    # Test loading
    print("\n🧪 Testing environment variable loading...")
    
    # Load the .env file to test
    try:
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    if value and not value.startswith('your_'):
                        print(f"✅ {key}: {'*' * len(value)}")
                    else:
                        print(f"⚠️  {key}: Not set")
    except Exception as e:
        print(f"❌ Error testing .env file: {e}")

if __name__ == "__main__":
    setup_environment()
