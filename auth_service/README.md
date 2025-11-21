# auth_service

## 🚀 Setup Instructions

1. Update .env file

2. Collect Static files in staticfiles folder
   `python manage.py collectstatic`
   
3. Create virtual environment 
   `python -m venv venv`
   
4. Activate the virtual environment
   `venv\Scripts\activate`

5. Install dependencies 
   `pip install -r requirements.txt`

6. Run migrations 
   `python manage.py migrate`

7. Start development server
   `python manage.py`

## 🧱 Apps Included
- auth_app


## Use uv instead of pip

1. Install uv(if not installed)
   `pip install uv`

2. Initialize the uv to create .toml file
   `uv init`

3. Sync the latest libraries added
   `uv add -r requirements.txt`

4. Update .env file

5. Collect Static files in staticfiles folder
   `python manage.py collectstatic`

6. Run migrations 
   `uv run manage.py migrate`

7. Start development server
   `uv run manage.py` 

