from rest_framework import serializers
from .models import Processes, ProcessSteps


class ProcessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Processes
        fields = "__all__"


class ProcessStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessSteps
        fields = "__all__"
