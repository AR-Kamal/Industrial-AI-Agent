from typing import cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import ChatMessageForm
from .models import Conversation
from .services import ChatService


@login_required
def chat_index(request: HttpRequest) -> HttpResponse:
    user = cast(User, request.user)
    conversation = None
    conversation_id = request.GET.get("conversation")
    if conversation_id:
        conversation = get_object_or_404(
            Conversation,
            pk=conversation_id,
            user=user,
        )
    return render(
        request,
        "chatbot/index.html",
        {
            "conversation": conversation,
            "conversations": Conversation.objects.filter(user=user)[:20],
            "chat_messages": (
                conversation.messages.all() if conversation is not None else ()
            ),
            "form": ChatMessageForm(
                initial={
                    "conversation_id": (
                        conversation.pk if conversation is not None else None
                    )
                }
            ),
        },
    )


@login_required
def send_message(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    user = cast(User, request.user)
    form = ChatMessageForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            "chatbot/partials/form_error.html",
            {"form": form},
            status=422,
        )
        return response

    conversation = None
    conversation_id = form.cleaned_data.get("conversation_id")
    if conversation_id:
        conversation = get_object_or_404(
            Conversation,
            pk=conversation_id,
            user=user,
        )

    turn = ChatService().submit(
        user=user,
        content=form.cleaned_data["message"],
        conversation=conversation,
    )

    if request.headers.get("HX-Request") != "true":
        return redirect(
            f"{reverse('chatbot:index')}?conversation={turn.conversation.pk}"
        )

    return render(
        request,
        "chatbot/partials/chat_turn.html",
        {"turn": turn},
    )
