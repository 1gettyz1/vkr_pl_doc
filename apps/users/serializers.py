from rest_framework import serializers
from django.contrib.auth.hashers import make_password
from .models import Users


class UserSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source="role_id.role_name", read_only=True)

    class Meta:
        model = Users
        fields = ("user_id", "login", "full_name", "password", "role_id", "role_name")
        extra_kwargs = {"password": {"write_only": True}}

    def create(self, validated_data):
        raw_password = validated_data.get("password", "")
        validated_data["password_hash"] = make_password(raw_password)
        return super().create(validated_data)


class AuthSerializer(serializers.Serializer):
    login = serializers.CharField()
    password = serializers.CharField()
