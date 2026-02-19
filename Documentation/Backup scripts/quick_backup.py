"""
quick_backup.py - One-Click Backup

Quick backup script - just double-click and run!
Backs up all Python files from working directory to backup folder.

Usage: Just run this script before making any changes to your code.
"""

import os
import shutil
from datetime import datetime

# Your directories
SOURCE = r"C:\Ian\Python\GetTextFromYouTube\DocAnalyser"
BACKUP = r"C:\Ian\Python\Backups\DocAnalyser backups"

print("=" * 50)
print("📦 QUICK BACKUP")
print("=" * 50)

# Create backup folder if needed
os.makedirs(BACKUP, exist_ok=True)

# Copy all .py files
copied = 0
for file in os.listdir(SOURCE):
    if file.endswith('.py'):
        shutil.copy2(os.path.join(SOURCE, file), os.path.join(BACKUP, file))
        print(f"✓ {file}")
        copied += 1

print("\n" + "=" * 50)
print(f"✅ SUCCESS! Backed up {copied} Python files")
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 50)

input("\nPress Enter to close...")
