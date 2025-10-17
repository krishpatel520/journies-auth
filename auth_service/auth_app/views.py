from django.shortcuts import render
from django.core.paginator import Paginator
from django.db import DatabaseError
from auth_app.models.entity1_model import Entity1
from auth_app.models.entity2_model import Entity2
from auth_service.logger import logger_object

logger = logger_object('auth_app.views')

def index(request):
    try:
        logger.info(f"Index view accessed by user: {request.user}")
        logger.debug("Fetching all Entity1 objects")
        
        items = Entity1.objects.select_related().order_by('-created_at')
        
        # Add pagination
        paginator = Paginator(items, 25)  # Show 25 items per page
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        logger.info(f"Retrieved page {page_obj.number} of {paginator.num_pages}")
        return render(request, 'auth_app/index.html', {'page_obj': page_obj})
        
    except DatabaseError as e:
        logger.error(f"Database error in index view: {e}")
        return render(request, 'auth_app/error.html', {'error': 'Database connection error'})
    except Exception as e:
        logger.error(f"Unexpected error in index view: {e}")
        return render(request, 'auth_app/error.html', {'error': 'An unexpected error occurred'})

