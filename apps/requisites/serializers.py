from rest_framework import serializers
from .models import Requisites, RequisiteLinks, RequisiteValues


class RequisiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Requisites
        fields = "__all__"


class RequisiteValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisiteValues
        fields = "__all__"


class RequisiteLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisiteLinks
        fields = "__all__"
