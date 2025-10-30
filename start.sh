#!/bin/bash
echo "Starting LawXpert Flask App..."
export PORT=${PORT:-5000}
python app.py
