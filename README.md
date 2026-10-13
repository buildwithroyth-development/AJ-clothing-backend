# AJ-clothing-backend

Backend API for AJ Clothing built with Django and Django REST Framework.

## Setup & Running

1. **Activate virtual environment**:
   ```bash
   # Windows PowerShell:
   .venv\Scripts\Activate.ps1
   # Or Windows CMD:
   .venv\Scripts\activate.bat
   # macOS/Linux:
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run migrations**:
   ```bash
   python manage.py migrate
   ```

4. **Start the development server**:
   ```bash
   python manage.py runserver
   ```

## Status: no longer used by the frontend

The AJ Clothing frontend now reads and writes **Firebase Realtime Database** directly (see the frontend repo's README), so this Django API is not called by the app. It is kept for reference only. Do not deploy it with real data, because it has no authentication.
