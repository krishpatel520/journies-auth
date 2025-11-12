# auth_service

## 🚀 Setup Instructions

1. Create virtual environment 
   `python -m venv venv`
   
2. Activate the virtual environment
 `venv\Scripts\activate`

2. Install dependencies 
   `pip install -r requirements.txt`

3. Run migrations 
   `python manage.py migrate`

4. Start development server
   `python manage.py runserver`

## 🧱 Apps Included
- auth_app


## Use uv instead of pip

1. Install uv(if not installed)
   `pip install uv`

2. Initialize the uv to create .toml file
   `uv init`

3. Sync the latest libraries added
`uv add -r requirements.txt`

4. Run migrations 
   `uv run manage.py migrate`

5. Start development server
   `uv run manage.py runserver` 

