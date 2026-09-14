import json

from app.errors import AppError
from app.providers.base import Completion
from app.public_web import PublicWeb
from tests.test_v1 import BROWSER, action, pair, save_key, signup, sql
from tests.test_v2 import FakeSpeech, chat
from tests.test_v3 import finish, send, setup

pytest_plugins = ["tests.test_v1"]


def test_configured_voice_memory_and_offline_device_capabilities(v1):
    from app.voice_api import speech

    client, path, runtime, _ = v1
    signup(client)
    save_key(client)
    client.app.dependency_overrides[speech] = lambda: FakeSpeech()
    device, _, _ = pair(client)
    sql(path, "UPDATE device SET last_seen=0")
    conversation, reply = chat(client, "Can you listen?", device=device)
    assert reply.status_code == 200
    prompt = runtime.calls[-1][0]["content"]
    assert '"talk_input": true' in prompt and '"speech_output": true' in prompt
    assert '"companion_online": false' in prompt
    assert '"persistent_memory": true' in prompt and '"memory_enabled": true' in prompt
    assert "Talk" in prompt and "silence-based auto-finish" in prompt
    chat(client, "I own realme Buds T500 Pro", conversation)
    chat(client, "What earbuds do I own?", conversation)
    assert "realme Buds T500 Pro" in str(runtime.calls[-1])
    assert "memory storage does not exist" in runtime.calls[-1][0]["content"]
    assert sql(path, "SELECT COUNT(*) FROM personal_memory")[0][0] == 0
    chat(client, "Remember that I own realme Buds T500 Pro", conversation)
    assert sql(path, "SELECT COUNT(*) FROM personal_memory")[0][0] == 1
    client.post("/api/memories/settings", headers=BROWSER, json={"enabled": False})
    chat(client, "Can you save memories?", conversation)
    assert '"memory_enabled": false' in runtime.calls[-1][0]["content"]
    assert '"persistent_memory": true' in runtime.calls[-1][0]["content"]


def test_unconfigured_voice_is_not_advertised_as_available(v1):
    from app.voice_api import speech

    class Unavailable:
        def status(self):
            return {"stt": False, "tts": False}

    client, _, runtime, _ = v1
    signup(client)
    save_key(client)
    client.app.dependency_overrides[speech] = lambda: Unavailable()
    chat(client, "Can you listen?")
    assert '"talk_input": false' in runtime.calls[-1][0]["content"]
    assert '"speech_output": false' in runtime.calls[-1][0]["content"]


def test_research_status_echo_enters_retrieval_and_no_placeholder_history(v1):
    client, _, _, runtime, web, conversation = setup(v1)

    async def status_echo(key, messages, tools):
        runtime.plans.append(messages)
        return Completion("Research request received. Page content is omitted from tool planning.")

    async def search(query):
        web.calls.append(("search", query))
        return [{"title": "Today's top news", "url": "https://example.com/news"}]

    runtime.plan = status_echo
    web.search = search
    for _ in range(2):
        reply = send(client, conversation, "search for today's top news")
        assert reply["action"]["tool"] == "search_web"
        assert finish(client, reply["action"]["id"])["status"] == "succeeded"
    assert len(runtime.summaries) == 2
    assert "omitted from tool planning" not in str(runtime.plans[-1])
    prompt = runtime.summaries[-1][0]["content"]
    assert "retrieved live public pages" in prompt
    assert "You currently have no tools, live web access" not in prompt
    assert "without tool access" in prompt
    turns = client.get(f"/api/conversations/{conversation}").json()["messages"]
    assert "omitted from tool planning" not in str(turns)
    _, rejected = chat(client, "What's new?", conversation)
    assert rejected.status_code == 502
    assert "omitted from tool planning" not in rejected.text


def test_broad_consumer_search_uses_discovery_descriptions_and_readable_article(v1):
    client, _, _, runtime, _, conversation = setup(v1)
    runtime.args = {
        "query": "best earbuds under 2000",
        "source_urls": ["https://example.com/guessed"],
    }
    web = PublicWeb()
    reads = []

    async def fetch(url):
        if url.startswith("https://www.bing.com/search?"):
            return (
                url,
                (
                    "<rss><channel>"
                    "<item><title>Top products</title><link>https://amazon.in/category</link>"
                    "<description>Best earbuds under 2000</description></item>"
                    "<item><title>Budget audio comparison</title><link>https://example.com/review</link>"
                    "<description>Earbuds under 2000 reviewed with battery and microphone tests"
                    "</description></item>"
                    "</channel></rss>"
                ),
                "application/rss+xml",
            )
        reads.append(url)
        if url.endswith("/review"):
            return (
                url,
                "<title>Budget audio</title><main>Earbuds under 2000 comparison.</main>",
                "text/html",
            )
        raise AppError("web_unavailable", "This source is unavailable.", 422)

    web.fetch = fetch
    client.app.state.research.web = web
    result = finish(client, send(client, conversation)["action"]["id"])
    assert result["status"] == "succeeded"
    assert reads[0] == "https://example.com/review"
    assert result["details"]["sources"][0]["url"] == "https://example.com/review"
    payload = json.loads(runtime.summaries[-1][-1]["content"])
    assert payload["untrusted_sources"][0]["content"] == "Earbuds under 2000 comparison."


def test_expired_confirmation_reports_approval_not_dispatch(v1):
    client, path, _, _ = v1
    signup(client)
    device, companion, _ = pair(client)
    pending = action(client, device).json()
    sql(path, "UPDATE action SET expires_at=0 WHERE id=?", (pending["id"],))
    result = client.get("/api/actions").json()[0]
    assert result["status"] == "expired"
    assert "Approval expired" in result["result"]
    assert client.post("/api/companion/poll", headers=companion).json()["action"] is None
