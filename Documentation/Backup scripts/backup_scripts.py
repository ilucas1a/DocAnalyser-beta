"""
backup_scripts.py - Backup Python Scripts Before Modifications

This script copies all Python files from your working directory to a backup folder.
Run this before making any changes so you can easily restore if needed.

Author: Created for DocAnalyser project
Date: October 31, 2025
"""

import os
import shutil
from datetime import datetime

# ==================== CONFIGURATION ====================
SOURCE_DIR = r"C:\Ian\Python\GetTextFromYouTube\DocAnalyser"
BACKUP_DIR = r"C:\Ian\Python\Backups\DocAnalyser backups"

# ==================== BACKUP FUNCTION ====================
def backup_python_scripts():
    """
    Copy all Python files from source to backup directory.
    Creates backup directory if it doesn't exist.
    Overwrites existing files in backup.
    """
    
    print("=" * 60)
    print("📦 DocAnalyser BACKUP SCRIPT")
    print("=" * 60)
    print(f"\nSource:      {SOURCE_DIR}")
    print(f"Destination: {BACKUP_DIR}")
    print(f"Time:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n" + "-" * 60)
    
    # Check if source directory exists
    if not os.path.exists(SOURCE_DIR):
        print(f"\n❌ ERROR: Source directory not found!")
        print(f"   {SOURCE_DIR}")
        print("\nPlease check the path and try again.")
        input("\nPress Enter to exit...")
        return False
    
    # Create backup directory if it doesn't exist
    if not os.path.exists(BACKUP_DIR):
        print(f"\n📁 Creating backup directory...")
        os.makedirs(BACKUP_DIR)
        print(f"   ✓ Created: {BACKUP_DIR}")
    
    # Find all Python files
    print(f"\n🔍 Scanning for Python files...")
    python_files = []
    
    for filename in os.listdir(SOURCE_DIR):
        if filename.endswith('.py'):
            python_files.append(filename)
    
    if not python_files:
        print("\n⚠️  No Python files found in source directory!")
        input("\nPress Enter to exit...")
        return False
    
    print(f"   Found {len(python_files)} Python file(s)")
    
    # Copy each file
    print(f"\n📋 Copying files...")
    copied_count = 0
    skipped_count = 0
    error_count = 0
    
    for filename in python_files:
        source_path = os.path.join(SOURCE_DIR, filename)
        backup_path = os.path.join(BACKUP_DIR, filename)
        
        try:
            shutil.copy2(source_path, backup_path)
            file_size = os.path.getsize(source_path)
            size_kb = file_size / 1024
            print(f"   ✓ {filename:<40} ({size_kb:>6.1f} KB)")
            copied_count += 1
            
        except Exception as e:
            print(f"   ✗ {filename:<40} ERROR: {str(e)}")
            error_count += 1
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 BACKUP SUMMARY")
    print("=" * 60)
    print(f"   ✓ Successfully copied:  {copied_count} file(s)")
    
    if error_count > 0:
        print(f"   ✗ Errors:               {error_count} file(s)")
    
    if copied_count > 0:
        print(f"\n✅ BACKUP COMPLETE!")
        print(f"\nYour files are safely backed up to:")
        print(f"   {BACKUP_DIR}")
        print(f"\nYou can now make changes to your scripts with confidence!")
    else:
        print(f"\n⚠️  NO FILES WERE BACKED UP")
    
    print("\n" + "=" * 60)
    
    return copied_count > 0


# ==================== RESTORE FUNCTION (BONUS!) ====================
def restore_from_backup():
    """
    Restore Python files from backup to working directory.
    Use this if you need to undo changes.
    """
    
    print("=" * 60)
    print("🔄 RESTORE FROM BACKUP")
    print("=" * 60)
    print(f"\nThis will copy files FROM backup TO working directory:")
    print(f"   From: {BACKUP_DIR}")
    print(f"   To:   {SOURCE_DIR}")
    print(f"\n⚠️  WARNING: This will OVERWRITE your current files!")
    
    confirm = input("\nAre you sure you want to restore? (type YES to confirm): ")
    
    if confirm.upper() != "YES":
        print("\n❌ Restore cancelled.")
        return False
    
    # Check if backup directory exists
    if not os.path.exists(BACKUP_DIR):
        print(f"\n❌ ERROR: Backup directory not found!")
        print(f"   {BACKUP_DIR}")
        return False
    
    # Find all Python files in backup
    python_files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')]
    
    if not python_files:
        print("\n⚠️  No Python files found in backup directory!")
        return False
    
    print(f"\n📋 Restoring {len(python_files)} file(s)...")
    restored_count = 0
    
    for filename in python_files:
        backup_path = os.path.join(BACKUP_DIR, filename)
        source_path = os.path.join(SOURCE_DIR, filename)
        
        try:
            shutil.copy2(backup_path, source_path)
            print(f"   ✓ Restored: {filename}")
            restored_count += 1
        except Exception as e:
            print(f"   ✗ Error restoring {filename}: {str(e)}")
    
    print(f"\n✅ Restored {restored_count} file(s)")
    print("\n" + "=" * 60)
    
    return restored_count > 0


# ==================== MAIN MENU ====================
def main():
    """Main menu for backup operations"""
    
    while True:
        print("\n")
        print("=" * 60)
        print("📦 DocAnalyser BACKUP UTILITY")
        print("=" * 60)
        print("\nWhat would you like to do?")
        print("\n1. 📦 Backup (copy scripts to backup folder)")
        print("2. 🔄 Restore (copy backup back to working folder)")
        print("3. 📂 Show Paths")
        print("4. ❌ Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == "1":
            backup_python_scripts()
            input("\nPress Enter to continue...")
            
        elif choice == "2":
            restore_from_backup()
            input("\nPress Enter to continue...")
            
        elif choice == "3":
            print("\n" + "=" * 60)
            print("📂 CONFIGURED PATHS")
            print("=" * 60)
            print(f"\nWorking Directory:")
            print(f"   {SOURCE_DIR}")
            print(f"   Exists: {os.path.exists(SOURCE_DIR)}")
            
            print(f"\nBackup Directory:")
            print(f"   {BACKUP_DIR}")
            print(f"   Exists: {os.path.exists(BACKUP_DIR)}")
            
            if os.path.exists(SOURCE_DIR):
                py_files = [f for f in os.listdir(SOURCE_DIR) if f.endswith('.py')]
                print(f"\nPython files in working directory: {len(py_files)}")
            
            if os.path.exists(BACKUP_DIR):
                py_files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.py')]
                print(f"Python files in backup directory: {len(py_files)}")
            
            print("\n" + "=" * 60)
            input("\nPress Enter to continue...")
            
        elif choice == "4":
            print("\n👋 Goodbye!\n")
            break
            
        else:
            print("\n❌ Invalid choice. Please enter 1, 2, 3, or 4.")
            input("\nPress Enter to continue...")


# ==================== RUN ====================
if __name__ == "__main__":
    main()
