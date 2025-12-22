from django.db import models

class Property(models.Model):
    """Property model from shared database"""
    id = models.BigAutoField(primary_key=True)
    tenant_id = models.UUIDField()
    property_name = models.CharField(max_length=255)
    
    class Meta:
        db_table = 'journies_property'
        managed = False
