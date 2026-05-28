from rest_framework import serializers
from .models import DocumentTypes, ProductionObjects


class DocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentTypes
        fields = "__all__"


class ProductionObjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionObjects
        fields = "__all__"
