#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from decouple import config

def main():

    port = config('PORT')
    base_route = config('BASE_ROUTE', default='')

    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'auth_service.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    if len(sys.argv) == 1:
        # Default to runserver using env-defined port
        sys.argv += ['runserver', f'0.0.0.0:{port}']
    
    # Only print startup info once (avoid double printing during auto-reload)
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver' and not os.environ.get('RUN_MAIN'):
        print(f"Starting Django app on port {port}")
        print(f"Direct Django: http://127.0.0.1:{port}/health/")
        print(f"Reverse proxy (through nginx): http://127.0.0.1{base_route}/health/\n")
        print(f"Reverse proxy (through nginx): http://127.0.0.1{base_route}/swagger/\n")
    
    try:
        execute_from_command_line(sys.argv)
    except Exception as e:
        print(f"Error starting Django: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
