import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def validate_role_id(role_id):
    """Validate role_id exists in Compass service"""
    if not role_id:
        return True  # role_id is optional
    
    try:
        compass_url = getattr(settings, 'COMPASS_SERVICE_URL', 'http://localhost:8002')
        response = requests.get(
            f'{compass_url}/api/roles/{role_id}/',
            timeout=5
        )
        
        if response.status_code == 200:
            logger.debug(f"Role {role_id} validated successfully")
            return True
        else:
            logger.warning(f"Role {role_id} not found in Compass service")
            return False
    except Exception as e:
        logger.error(f"Failed to validate role_id {role_id}: {e}")
        return False
