"""Read-only organization-scoped endpoint for the FinAudit Copilot."""

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_assistant import answer_known_question, answer_question, build_context
from .permissions import IsMemberOfOrganization


class AssistantRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000, trim_whitespace=True)
    run_id = serializers.UUIDField(required=False)
    transaction_reconciliation_id = serializers.UUIDField(required=False)
    conversation = serializers.ListField(
        child=serializers.DictField(), required=False, max_length=6,
    )

    def validate_conversation(self, value):
        cleaned = []
        for item in value:
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                raise serializers.ValidationError("Conversation entries must contain a role and text content.")
            cleaned.append({"role": role, "content": content[:1000]})
        return cleaned


class AssistantView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsMemberOfOrganization]

    def post(self, request, org_id):
        serializer = AssistantRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            context = build_context(
                organization=request.organization,
                run_id=serializer.validated_data.get("run_id"),
                transaction_reconciliation_id=serializer.validated_data.get("transaction_reconciliation_id"),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)})
        answer = answer_known_question(
            question=serializer.validated_data["question"],
            organization=request.organization,
            run_id=serializer.validated_data.get("run_id"),
            transaction_reconciliation_id=serializer.validated_data.get("transaction_reconciliation_id"),
            conversation=serializer.validated_data.get("conversation", []),
        )
        if answer is None:
            answer = answer_question(question=serializer.validated_data["question"], context=context)
        return Response({"answer": answer})
