from django.db import models

class Role(models.Model):
    """Role model - shared with compass service"""
    name = models.CharField(max_length=100)
    
    class Meta:
        db_table = 'journies_role'
        managed = False
    
    def __str__(self):
        return self.name
