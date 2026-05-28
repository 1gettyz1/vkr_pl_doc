from rest_framework import serializers
from .models import DocumentLinks, Documents


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documents
        fields = "__all__"


class DocumentLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentLinks
        fields = "__all__"
