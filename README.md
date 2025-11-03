# Introduction 
TODO: Give a short introduction of your project. Let this section explain the objectives or the motivation behind this project. 

# Getting Started
TODO: Guide users through getting your code up and running on their own system. In this section you can talk about:
1.	Installation process
2.	Software dependencies
3.	Latest releases
4.	API references

# Build and Test
TODO: Describe and show how to build your code and run the tests. 

# Contribute
TODO: Explain how other users and developers can contribute to make your code better. 

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)




--------------------------------------------------------------


# Auth Service Setup (Port 8001)

## Prerequisites

- Python 3.12+
- PostgreSQL 14+
- Redis 6+
- Django 4.2+

## Installation

### 1. Clone and Navigate
```bash
cd auth_service
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup PostgreSQL Database

Create database:
```bash
createdb users_db_journies
```

Or using psql:
```sql
CREATE DATABASE users_db_journies;
```

### 5. Configure Environment

Create `.env` file in `auth_service/` directory:
```
# Database
DATABASE_URL=postgresql://postgres:Rohit123@localhost:5432/users_db_journies

# Redis (for pub/sub to data-sync-service)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_CHANNEL=user_created

# JWT
SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=RS256

# Debug
DEBUG=True
```

### 6. Run Migrations
```bash
python manage.py migrate
```

### 7. Create Superuser (Optional)
```bash
python manage.py createsuperuser
```

## Running the Service

```bash
python manage.py runserver 0.0.0.0:8001
```

Service will be available at: `http://localhost:8001`

## API Endpoints

- **Signup:** `POST /api/v1/users/signup/`
- **Login:** `POST /api/v1/users/login/`
- **Create User:** `POST /api/v1/users/`
- **List Users:** `GET /api/v1/users/`
- **Get User:** `GET /api/v1/users/{id}/`
- **Update User:** `PUT /api/v1/users/{id}/`
- **Delete User:** `DELETE /api/v1/users/{id}/`

## Important Notes

- **Redis Required:** This service publishes user events to Redis channel `user_created`
- **Data-Sync Service Listens:** The data-sync-service (port 7001) listens to these events and syncs to Qdrant
- **Tenant Isolation:** Uses PostgreSQL Row-Level Security (RLS) for multi-tenant data isolation

## Troubleshooting

**Redis Connection Error:**
```bash
# Start Redis
redis-server
```

**Database Connection Error:**
```bash
# Check PostgreSQL is running
psql -U postgres -d users_db_journies
```

**Port Already in Use:**
```bash
# Change port in command
python manage.py runserver 0.0.0.0:8002
```

