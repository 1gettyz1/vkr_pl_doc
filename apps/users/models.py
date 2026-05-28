from django.db import models


class Users(models.Model):
    user_id = models.BigAutoField(primary_key=True)
    login = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=255)
    password = models.CharField(max_length=255, default="changeme")
    password_hash = models.CharField(max_length=255, blank=True)
    role_id = models.ForeignKey("roles.Roles", on_delete=models.PROTECT, related_name="users")

    class Meta:
        db_table = "Users"

    def __str__(self):
        return self.full_name
