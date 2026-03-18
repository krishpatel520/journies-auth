from django.db import models

class Department(models.Model):
    """Department model - shared with compass service"""
    name = models.CharField(max_length=100)
 
    
    class Meta:
        db_table = 'journies_department_master'
        managed = False
    
    def __str__(self):
        return self.name
