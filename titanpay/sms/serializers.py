from rest_framework import serializers
from sms.models import SMS


class SMSSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMS
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['device'] = instance.device.owner
        representation['order_in'] = str(instance.inorder.get().id) if instance.inorder.exists() else None
        representation['order_out'] = str(instance.outorder.get().id) if instance.outorder.exists() else None
        return representation