#!/bin/bash

# Initialization script for Threads Traffic Management System

# Display ASCII art
echo "
  _____  _                        _   
 |_   _|| |_  _ _  ___  ___  ___ | |_ 
   | |  | '_|| '_|/ -_)/ -_)/ _ \\| ' \\
   |_|  |_|  |_|  \\___|\\___|\\_,_||_||_|
 _____            __   __  _         
|_   _| _ _  __ _ / _| / _|(_) ___   
  | |  | '_|/ _\` |  _||  _|| |/ __| 
  |_|  |_|  \\__,_|_|  |_|  |_|\\___| 
 __  __                                                   _   
|  \\/  | __ _  _ _   __ _  __ _  ___  _ __   ___  _ _  | |_ 
| |\\/| |/ _\` || ' \\ / _\` |/ _\` |/ -_)| '  \\ / -_)| ' \\ |  _|
|_|  |_|\\__,_||_||_|\\__,_|\\__, |\\___||_|_|_|\\___||_||_| \\__|
                          |___/                              
"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')
read -r major minor <<< "$PYTHON_VERSION"
if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
    echo "Error: Python 3.10 or higher is required. Found Python $major.$minor"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "Please edit the .env file with your configuration"
else
    echo ".env file already exists"
fi

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p data logs

# Initialize the database
echo "Initializing database..."
python database/init_db.py

echo "
Initialization complete!

To start the system:
    1. Edit the .env file with your configuration
    2. Run: python main.py

For Docker deployment:
    docker-compose up -d

The dashboard will be available at: http://localhost:8501
" 