from django.db import models
from django.core.validators import MinLengthValidator, MaxLengthValidator

class Entity1(models.Model):
    name = models.CharField(
        max_length=100,
        validators=[
            MinLengthValidator(2, 'Name must be at least 2 characters long'),
            MaxLengthValidator(100, 'Name cannot exceed 100 characters')
        ],
        db_index=True,
        help_text='Enter entity name (2-100 characters)'
    )
    description = models.TextField(
        blank=True,
        max_length=1000,
        help_text='Optional description (max 1000 characters)'
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Whether this entity is active'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Entity 1'
        verbose_name_plural = 'Entity 1 Records'
        indexes = [
            models.Index(fields=['is_active', 'created_at']),
            models.Index(fields=['name']),
        ]
        # constraints = [
        #     models.CheckConstraint(
        #         check=models.Q(name__length__gte=2),
        #         name='entity1_name_min_length'
        #     ),
        # ]

    def __str__(self):
        return self.name
    
    def clean(self):
        if self.name:
            self.name = self.name.strip()
