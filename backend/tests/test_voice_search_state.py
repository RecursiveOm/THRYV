import pytest

from app.errors import AppError
from app.research import retry_query, search_candidates
from tests.test_v1 import BROWSER, save_key, signup
from tests.test_v2 import chat
from tests.test_v3 import finish, send, setup

pytest_plugins = ["tests.test_v1"]


@pytest.mark.parametrize("available,enabled", [(True, False), (True, True), (False, False)])
def test_voice_and_owned_wake_state_reach_capability_prompt(v1, available, enabled):
    from app.voice_api import speech

    class Voice:
        def status(self):
            return {"stt": available, "tts": available, "wake": available}

    client, _, runtime, _ = v1
    signup(client)
    save_key(client)
    client.app.dependency_overrides[speech] = lambda: Voice()
    client.post("/api/voice/settings", headers=BROWSER, json={"wake_enabled": enabled})
    _, response = chat(client, "Can you listen?")
    assert response.status_code == 200
    prompt = runtime.calls[-1][0]["content"]
    assert f'"talk_input": {str(available).lower()}' in prompt
    assert f'"wake_available": {str(available).lower()}' in prompt
    assert f'"wake_enabled": {str(enabled).lower()}' in prompt
    assert '"wake_keyword": "THRYV"' in prompt
    assert "lead with Talk" in prompt and "Wake word (Beta)" in prompt
    assert "Never claim wake mode does not exist" in prompt
    assert "do not claim the microphone is currently active" in prompt


@pytest.mark.parametrize(
    "query,message",
    [
        ("best earbuds under 2000 India current prices", "search for best earbuds under 2000"),
        ("today's top news headlines updated", "search for today's top news"),
    ],
)
def test_poor_provider_results_retry_original_topic(v1, query, message):
    client, _, _, runtime, web, conversation = setup(v1)
    runtime.args = {"query": query, "source_urls": []}
    searches = []

    async def search(text):
        searches.append(text)
        if len(searches) == 1:
            return [
                {"title": "Dictionary definition", "url": "https://dictionary.example/definition"}
            ]
        return [{"title": text, "url": "https://readable.example/article"}]

    web.search = search
    result = finish(client, send(client, conversation, message)["action"]["id"])
    assert result["status"] == "succeeded"
    assert searches == [query, retry_query(query, message)]
    assert result["details"]["sources"][0]["url"] == "https://readable.example/article"


def test_diverse_domains_precede_repeated_blocked_host():
    results = [
        {"title": "best earbuds under 2000", "url": f"https://blocked.example/{i}"}
        for i in range(5)
    ] + [{"title": "earbuds under 2000 review", "url": "https://readable.example/review"}]
    candidates = search_candidates("best earbuds under 2000", results, [])
    assert candidates[:2] == ["https://blocked.example/0", "https://readable.example/review"]


def test_unreadable_results_retry_without_repeating_urls(v1):
    client, _, _, runtime, web, conversation = setup(v1)
    runtime.args = {"query": "best earbuds under 2000", "source_urls": []}
    searches, reads = [], []
    original_read = web.read

    async def search(query):
        searches.append(query)
        if len(searches) == 1:
            return [
                {"title": query, "url": f"https://blocked{i}.example/article"} for i in range(3)
            ]
        return [{"title": query, "url": "https://readable.example/article"}]

    async def read(url):
        reads.append(url)
        if "blocked" in url:
            raise AppError("web_unavailable", "Public page unavailable.", 422)
        return await original_read(url)

    web.search, web.read = search, read
    result = finish(
        client, send(client, conversation, "search for best earbuds under 2000")["action"]["id"]
    )
    assert result["status"] == "succeeded"
    assert searches == ["best earbuds under 2000", "earbuds under 2000"]
    assert len(reads) == len(set(reads)) == 4


def test_official_document_query_preserves_fetched_hint(v1):
    client, _, _, runtime, web, conversation = setup(v1)
    runtime.args = {
        "query": "FastAPI official deployment docs",
        "source_urls": ["https://fastapi.tiangolo.com/deployment/"],
    }
    result = finish(
        client,
        send(client, conversation, "Research official FastAPI deployment docs")["action"]["id"],
    )
    assert result["status"] == "succeeded"
    assert result["details"]["sources"][0]["url"] == "https://fastapi.tiangolo.com/deployment/"
    assert len([c for c in web.calls if c[0] == "search"]) == 1
