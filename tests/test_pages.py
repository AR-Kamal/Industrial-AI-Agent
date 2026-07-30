import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_home_page_is_public(client) -> None:
    response = client.get(reverse("home"))

    assert response.status_code == 200
    assert b"FANUC ER-4iA" in response.content


@pytest.mark.django_db
def test_login_page_responds(client) -> None:
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert b"Log in" in response.content


@pytest.mark.django_db
def test_chat_page_requires_login(client) -> None:
    url = reverse("chatbot:index")
    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={url}"


@pytest.mark.django_db
def test_authenticated_user_can_open_chat(client) -> None:
    user = get_user_model().objects.create_user(
        username="reviewer",
        password="local-test-password",
    )
    client.force_login(user)

    response = client.get(reverse("chatbot:index"))

    assert response.status_code == 200
    assert b"Start a local conversation" in response.content
    assert b"Local Ollama" in response.content


@pytest.mark.django_db
def test_logout_requires_post(client) -> None:
    response = client.get(reverse("logout"))

    assert response.status_code == 405


@pytest.mark.django_db
def test_custom_404_page_is_safe(client, settings) -> None:
    settings.DEBUG = False

    response = client.get("/page-that-does-not-exist/")

    assert response.status_code == 404
    assert b"Page not found" in response.content
