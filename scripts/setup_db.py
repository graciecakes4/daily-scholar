#!/usr/bin/env python3
"""
Database Setup Script for Daily Scholar

Run this script once to initialize the SQLite database:
    python scripts/setup_db.py

This will:
1. Create the data directory if it doesn't exist
2. Create all database tables
3. Verify the setup
"""

import sys
from pathlib import Path

# Add backend to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import create_tables, Base


def main():
    print("=" * 50)
    print("Daily Scholar - Database Setup")
    print("=" * 50)
    print()
    
    # Create data directory
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    print(f"✓ Data directory: {data_dir}")
    
    # Create uploads directory
    uploads_dir = Path(__file__).parent.parent / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    print(f"✓ Uploads directory: {uploads_dir}")
    
    # Create tables
    print()
    print("Creating database tables...")
    engine = create_tables()
    
    # List created tables
    print()
    print("Tables created:")
    for table_name in Base.metadata.tables.keys():
        print(f"  - {table_name}")
    
    print()
    print("=" * 50)
    print("✅ Database setup complete!")
    print()
    print("Next steps:")
    print("1. Copy .env.example to .env and add your API keys")
    print("2. Run the backend: cd backend && uvicorn main:app --reload")
    print("3. Visit http://localhost:8000/docs to test the API")
    print("=" * 50)


if __name__ == "__main__":
    main()
