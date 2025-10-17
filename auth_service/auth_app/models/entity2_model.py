from django.db import models
from django.core.validators import MinLengthValidator

class Entity2(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('draft', 'Draft'),
        ('archived', 'Archived'),
    ]
    
    title = models.CharField(
        max_length=100,
        validators=[
            MinLengthValidator(3, 'Title must be at least 3 characters long')
        ],
        db_index=True,
        help_text='Enter title (3-100 characters)'
    )
    content = models.TextField(
        blank=True,
        max_length=5000,
        help_text='Optional content (max 5000 characters)'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        db_index=True,
        help_text='Current status of the entity'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Entity 2'
        verbose_name_plural = 'Entity 2 Records'
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['title']),
        ]
        # constraints = [
        #     models.CheckConstraint(
        #         check=models.Q(title__length__gte=3),
        #         name='entity2_title_min_length'
        #     ),
        # ]

    def __str__(self):
        return self.title
    
    def clean(self):
        if self.title:
            self.title = self.title.strip()
