from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db import DatabaseError
from auth_app.models.user_model import UserModel
from auth_service.logger import logger_object

logger = logger_object('auth_app.views')

def index(request):
    try:
        logger.info(f"Index view accessed by user: {request.user}")
        logger.debug("Fetching all UserModel objects")
        
        items = UserModel.objects.order_by('-created_at')
        
        # Add pagination
        paginator = Paginator(items, 25)  # Show 25 items per page
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        users_data = [{
            'id': user.id,
            'email': user.email,
            'created_at': user.created_at
        } for user in page_obj]
        
        logger.info(f"Retrieved page {page_obj.number} of {paginator.num_pages}")
        return JsonResponse({
            'users': users_data,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        })
        
    except DatabaseError as e:
        logger.error(f"Database error in index view: {e}")
        return JsonResponse({'error': 'Database connection error'}, status=500)
    except Exception as e:
        logger.error(f"Unexpected error in index view: {e}")
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)

