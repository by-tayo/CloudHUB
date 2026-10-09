"""Offline tests for bot.py: helpers, plus the three commands run against a
fake WebDAV + Ollama server. Run with:  python -m pytest -q test_bot.py
"""

import asyncio
import io
import os
import types

import pytest
from aiohttp import web

os.environ.update(
    DISCORD_TOKEN="x", GUILD_ID="1", ALLOWED_USER_IDS="42", CHANNEL_ID="7",
    NC_USER="discord-bot", NC_APP_PASSWORD="pw", NC_INBOX="Discord Inbox",
    OLLAMA_MODEL="llama3.2:3b",
)

import bot  # noqa: E402


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("raw,expected", [
    ("Discord Inbox/notes.md", "Discord Inbox/notes.md"),
    ("/Discord Inbox/notes.md/", "Discord Inbox/notes.md"),
    ("a\\b.txt", "a/b.txt"),
])
def test_safe_relpath_ok(raw, expected):
    assert bot.safe_relpath(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "../etc/passwd", "a/../b", "a/./b", "a//b"])
def test_safe_relpath_rejects(raw):
    with pytest.raises(ValueError):
        bot.safe_relpath(raw)


def test_safe_filename():
    assert bot.safe_filename("../../evil.txt") == "evil.txt"
    assert bot.safe_filename("C:\\x\\report.pdf") == "report.pdf"
    with pytest.raises(ValueError):
        bot.safe_filename("..")


def test_dav_url_encodes():
    url = bot.dav_url("https://nc", "discord-bot", "Discord Inbox/a#b?.md")
    assert url == "https://nc/remote.php/dav/files/discord-bot/Discord%20Inbox/a%23b%3F.md"


def test_chunk_message():
    text = ("line\n" * 1000).strip()
    chunks = bot.chunk_message(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")
    assert bot.chunk_message("") == ["(empty response)"]


def test_extract_text():
    assert bot.extract_text("a.md", b"# hi") == "# hi"
    with pytest.raises(ValueError):
        bot.extract_text("a.exe", b"MZ")


def test_extract_pdf():
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(100, 100)
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(ValueError, match="no extractable text"):
        bot.extract_text("scan.pdf", buf.getvalue())


# ------------------------------------------------- fake Nextcloud + Ollama

class FakeServer:
    def __init__(self):
        self.files = {}   # path -> bytes
        self.dirs = set()
        self.prompts = []

    def app(self):
        app = web.Application()
        app.router.add_route("*", "/remote.php/dav/files/{user}/{path:.*}", self.dav)
        app.router.add_post("/v1/chat/completions", self.chat)
        return app

    async def dav(self, request):
        assert request.match_info["user"] == "discord-bot"
        assert request.headers.get("Authorization", "").startswith("Basic ")
        path = request.match_info["path"]
        if request.method == "MKCOL":
            if path in self.dirs:
                return web.Response(status=405)
            self.dirs.add(path)
            return web.Response(status=201)
        if request.method == "PROPFIND":
            return web.Response(status=207 if path in self.files or path in self.dirs else 404)
        if request.method == "PUT":
            self.files[path] = await request.read()
            return web.Response(status=201)
        if request.method == "GET":
            if path not in self.files:
                return web.Response(status=404)
            return web.Response(body=self.files[path])
        return web.Response(status=405)

    async def chat(self, request):
        body = await request.json()
        assert body["model"] == "llama3.2:3b"
        self.prompts.append(body["messages"][1]["content"])
        return web.json_response({"choices": [{"message": {"content": "- point one\n- point two"}}]})


class FakeResponse:
    def __init__(self, log):
        self.log = log

    async def send_message(self, content, ephemeral=False):
        self.log.append(("ephemeral" if ephemeral else "msg", content))

    async def defer(self, thinking=False):
        self.log.append(("defer", thinking))


class FakeFollowup:
    def __init__(self, log):
        self.log = log

    async def send(self, content):
        self.log.append(("followup", content))


def fake_interaction(user_id=42, channel_id=7, category_id=None, parent_category=None):
    log = []
    parent = types.SimpleNamespace(category_id=parent_category) if parent_category else None
    channel = types.SimpleNamespace(category_id=category_id, parent=parent)
    return types.SimpleNamespace(
        user=types.SimpleNamespace(id=user_id), channel_id=channel_id, channel=channel, id=999,
        response=FakeResponse(log), followup=FakeFollowup(log), log=log,
    ), log


class FakeAttachment:
    def __init__(self, filename, data):
        self.filename, self.data, self.size = filename, data, len(data)

    async def read(self):
        return self.data


@pytest.fixture
def env():
    async def start():
        fake = FakeServer()
        runner = web.AppRunner(fake.app())
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        os.environ["NC_URL"] = f"http://127.0.0.1:{port}"
        os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{port}/v1"
        client = bot.CloudHubBot(bot.Config())
        import aiohttp
        client.session = aiohttp.ClientSession()
        client.nc = bot.Nextcloud(client.cfg, client.session)
        client.ollama = bot.Ollama(client.cfg, client.session)
        bot.register_commands(client)
        return fake, runner, client
    return start


def cmd(client, name):
    return client.tree.get_command(name).callback


def run(coro):
    return asyncio.run(coro)


def test_commands_end_to_end(env):
    async def scenario():
        fake, runner, client = await env()
        try:
            # /upload into a new subfolder
            i, log = fake_interaction()
            await cmd(client, "upload")(i, FakeAttachment("notes.md", b"# CloudHUB notes\nZFS rocks"), "school")
            assert fake.files["Discord Inbox/school/notes.md"] == b"# CloudHUB notes\nZFS rocks"
            assert "Discord Inbox" in fake.dirs and "Discord Inbox/school" in fake.dirs
            assert log[-1][1].startswith("✅")

            # same name again -> not overwritten, gets a suffix
            i, log = fake_interaction()
            await cmd(client, "upload")(i, FakeAttachment("notes.md", b"v2"), "school")
            assert fake.files["Discord Inbox/school/notes-999.md"] == b"v2"

            # /summarize the uploaded file
            i, log = fake_interaction()
            await cmd(client, "summarize")(i, "Discord Inbox/school/notes.md")
            assert "ZFS rocks" in fake.prompts[-1]
            assert "point one" in log[-1][1]

            # /summarize a missing file -> friendly error
            i, log = fake_interaction()
            await cmd(client, "summarize")(i, "Discord Inbox/nope.md")
            assert log[-1][1].startswith("❌") and "not found" in log[-1][1]

            # traversal attempt
            i, log = fake_interaction()
            await cmd(client, "summarize")(i, "../admin/secret.md")
            assert log[-1][1].startswith("❌")

            # /ask
            i, log = fake_interaction()
            await cmd(client, "ask")(i, "What is ZFS?")
            assert fake.prompts[-1] == "What is ZFS?"
            assert "point two" in log[-1][1]

            # wrong user and wrong channel are refused before any work
            i, log = fake_interaction(user_id=1)
            await cmd(client, "ask")(i, "hi")
            assert log == [("ephemeral", "You're not allowed to use this bot.")]
            i, log = fake_interaction(channel_id=8)
            await cmd(client, "ask")(i, "hi")
            assert log[0][0] == "ephemeral" and "<#7>" in log[0][1]
        finally:
            await client.session.close()
            await runner.cleanup()

    run(scenario())


def test_ollama_unreachable(env):
    async def scenario():
        fake, runner, client = await env()
        try:
            client.cfg.ollama_url = "http://127.0.0.1:1/v1"
            i, log = fake_interaction()
            await cmd(client, "ask")(i, "hello")
            assert "Can't reach Ollama" in log[-1][1]
        finally:
            await client.session.close()
            await runner.cleanup()

    run(scenario())


# ---------------------------------------------------------------- health

MEMINFO = "MemTotal:        2000000 kB\nMemAvailable:     200000 kB\nSwapTotal:       2000000 kB\nSwapFree:        1000000 kB\n"


def test_parse_meminfo():
    info = bot.parse_meminfo(MEMINFO)
    assert info["MemTotal"] == 2000000 and info["SwapFree"] == 1000000


def test_check_memory_and_disk(tmp_path):
    mem = tmp_path / "meminfo"
    mem.write_text(MEMINFO)
    cfg = bot.Config()
    cfg.meminfo_path = str(mem)
    key, ok, detail = bot.check_memory(cfg)
    assert key == "ec2-memory" and ok is False and "90% used" in detail and "swap 50%" in detail
    cfg.disk_probe = str(tmp_path)
    key, ok, detail = bot.check_disk(cfg)
    assert key == "ec2-disk" and "GB free" in detail
    cfg.disk_probe = str(tmp_path / "missing")
    assert bot.check_disk(cfg)[1] is True  # unmounted probe is skipped, not an alert


def test_diff_alerts():
    state = {}
    assert bot.diff_alerts(state, [("a", True, "A fine"), ("b", False, "B bad")]) == ["⚠️ B bad"]
    assert bot.diff_alerts(state, [("a", True, "A fine"), ("b", False, "B bad")]) == []  # no repeats
    assert bot.diff_alerts(state, [("a", False, "A bad"), ("b", True, "B fine")]) == ["⚠️ A bad", "✅ Recovered: B fine"]


class HealthServer(FakeServer):
    def __init__(self, pool_alloc=50, alerts=()):
        super().__init__()
        self.pool_alloc, self.alerts = pool_alloc, list(alerts)

    def app(self):
        app = super().app()
        app.router.add_get("/status.php", lambda r: web.json_response({"installed": True}))
        app.router.add_get("/v1/models", lambda r: web.json_response({"data": [{"id": "llama3.2:3b"}]}))
        app.router.add_get("/api/v2.0/pool", self.pool)
        app.router.add_get("/api/v2.0/alert/list", self.alert_list)
        return app

    async def pool(self, request):
        assert request.headers["Authorization"] == "Bearer key123"
        return web.json_response([{"name": "tank", "status": "ONLINE", "healthy": True, "size": 100, "allocated": self.pool_alloc}])

    async def alert_list(self, request):
        return web.json_response(self.alerts)


def test_status_and_truenas_checks():
    async def scenario():
        fake = HealthServer(pool_alloc=85, alerts=[
            {"level": "WARNING", "formatted": "Pool tank is 85% full", "dismissed": False},
            {"level": "INFO", "formatted": "update available", "dismissed": False},
            {"level": "CRITICAL", "formatted": "old thing", "dismissed": True},
        ])
        runner = web.AppRunner(fake.app())
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        os.environ.update(NC_URL=f"http://127.0.0.1:{port}", OLLAMA_URL=f"http://127.0.0.1:{port}/v1",
                          TRUENAS_URL=f"http://127.0.0.1:{port}", TRUENAS_API_KEY="key123")
        import aiohttp
        client = bot.CloudHubBot(bot.Config())
        client.session = aiohttp.ClientSession()
        client.nc = bot.Nextcloud(client.cfg, client.session)
        client.ollama = bot.Ollama(client.cfg, client.session)
        bot.register_commands(client)
        try:
            checks = {k: (ok, d) for k, ok, d in await bot.run_checks(client)}
            assert checks["nextcloud"][0] and checks["ollama"][0]
            assert checks["pool-tank-health"] == (True, "Pool tank: ONLINE, 85% used")
            assert checks["pool-tank-capacity"][0] is False
            assert checks["truenas-alerts"][0] is False and "85% full" in checks["truenas-alerts"][1]
            assert "update available" not in checks["truenas-alerts"][1]  # INFO filtered
            assert "old thing" not in checks["truenas-alerts"][1]        # dismissed filtered

            i, log = fake_interaction()
            await cmd(client, "status")(i)
            out = log[-1][1]
            assert out.startswith("**CloudHUB status**") and "🟢 Nextcloud: reachable" in out and "🔴 Pool tank capacity" in out

            # TrueNAS down -> one clear alert instead of a crash
            client.cfg.truenas_url = "http://127.0.0.1:1"
            down = await bot.check_truenas(client.cfg, client.session)
            assert down == [("truenas", False, "TrueNAS: unreachable (is the Surface awake and the VM running?)")]
        finally:
            for k in ("TRUENAS_URL", "TRUENAS_API_KEY"):
                os.environ.pop(k, None)
            await client.session.close()
            await runner.cleanup()

    run(scenario())


def test_category_and_alert_channel():
    cfg = bot.Config()
    assert cfg.alert_channel_id == 7  # defaults to the first allowed channel
    cfg.channel_ids, cfg.category_id = set(), 500
    i, _ = fake_interaction(channel_id=8, category_id=500)
    assert bot.channel_allowed(cfg, i)                      # channel in the category
    i, _ = fake_interaction(channel_id=9, category_id=None, parent_category=500)
    assert bot.channel_allowed(cfg, i)                      # thread under a category channel
    i, _ = fake_interaction(channel_id=8, category_id=600)
    assert not bot.channel_allowed(cfg, i)                  # different category
    cfg.category_id = None
    assert bot.channel_allowed(cfg, i)                      # no limits set -> allowed
    os.environ.update(CHANNEL_ID="", CATEGORY_ID="500", ALERT_CHANNEL_ID="77", ALLOWED_USER_IDS="42, 43")
    try:
        cfg2 = bot.Config()
        assert cfg2.channel_ids == set() and cfg2.category_id == 500
        assert cfg2.alert_channel_id == 77 and cfg2.allowed_users == {42, 43}
    finally:
        os.environ.update(CHANNEL_ID="7", ALLOWED_USER_IDS="42")
        os.environ.pop("CATEGORY_ID"); os.environ.pop("ALERT_CHANNEL_ID")


# ------------------------------------------------- docx + inbox autocomplete

def make_docx(paragraphs):
    import zipfile as zf
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    buf = io.BytesIO()
    with zf.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_docx_text():
    data = make_docx(["CloudHUB &amp; TrueNAS", "Zero inbound ports."])
    assert bot.extract_text("post.docx", data) == "CloudHUB & TrueNAS\nZero inbound ports."
    with pytest.raises(ValueError, match="valid Word"):
        bot.extract_text("bad.docx", b"not a zip")


MULTISTATUS = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
 <d:response><d:href>/remote.php/dav/files/discord-bot/Discord%20Inbox/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
 <d:response><d:href>/remote.php/dav/files/discord-bot/Discord%20Inbox/CloudHUB_Post.docx</d:href>
  <d:propstat><d:prop><d:resourcetype/></d:prop></d:propstat></d:response>
 <d:response><d:href>/remote.php/dav/files/discord-bot/Discord%20Inbox/school/</d:href>
  <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
</d:multistatus>"""


def test_parse_propfind():
    got = bot.parse_propfind(MULTISTATUS, "/remote.php/dav/files/discord-bot/")
    assert ("Discord Inbox/CloudHUB_Post.docx", False) in got
    assert ("Discord Inbox/school", True) in got


def test_autocomplete_and_docx_summary():
    async def scenario():
        fake = FakeServer()
        fake.files["Discord Inbox/CloudHUB_Post.docx"] = make_docx(["Hybrid cloud with ZFS at home."])
        fake.files["Discord Inbox/school/notes.md"] = b"# notes"
        fake.dirs.update({"Discord Inbox", "Discord Inbox/school"})

        async def propfind(request):
            from urllib.parse import quote as q
            path = request.match_info["path"].strip("/")
            if request.method != "PROPFIND":
                return await fake.dav(request)
            if path not in fake.dirs and path not in fake.files:
                return web.Response(status=404)
            base = "/remote.php/dav/files/discord-bot/"
            entries = [(path, path in fake.dirs)]
            if path in fake.dirs and request.headers.get("Depth") == "1":
                for p in list(fake.files) + list(fake.dirs):
                    if p.rsplit("/", 1)[0] == path and "/" in p:
                        entries.append((p, p in fake.dirs))
            rows = "".join(
                f"<d:response><d:href>{base}{q(p)}{'/' if d else ''}</d:href><d:propstat><d:prop><d:resourcetype>"
                f"{'<d:collection/>' if d else ''}</d:resourcetype></d:prop></d:propstat></d:response>" for p, d in entries)
            return web.Response(status=207, text=f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">{rows}</d:multistatus>')

        app = web.Application()
        app.router.add_route("*", "/remote.php/dav/files/{user}/{path:.*}", propfind)
        app.router.add_post("/v1/chat/completions", fake.chat)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        os.environ["NC_URL"] = f"http://127.0.0.1:{port}"
        os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{port}/v1"
        import aiohttp
        client = bot.CloudHubBot(bot.Config())
        client.session = aiohttp.ClientSession()
        client.nc = bot.Nextcloud(client.cfg, client.session)
        client.ollama = bot.Ollama(client.cfg, client.session)
        bot.register_commands(client)
        try:
            files = await client.nc.list_files("Discord Inbox")
            assert files == ["Discord Inbox/CloudHUB_Post.docx", "Discord Inbox/school/notes.md"]

            ac = client.tree.get_command("summarize")._params["path"].autocomplete
            i, _ = fake_interaction()
            choices = await ac(i, "cloud")
            assert [c.value for c in choices] == ["Discord Inbox/CloudHUB_Post.docx"]
            i, _ = fake_interaction(user_id=1)
            assert await ac(i, "") == []          # strangers get no file list

            i, log = fake_interaction()
            await cmd(client, "summarize")(i, "Discord Inbox/CloudHUB_Post.docx")
            assert "ZFS at home" in fake.prompts[-1] and "point one" in log[-1][1]
        finally:
            await client.session.close()
            await runner.cleanup()

    run(scenario())


def test_long_prompt_shows_ellipsis(env):
    async def scenario():
        fake, runner, client = await env()
        try:
            i, log = fake_interaction()
            await cmd(client, "ask")(i, "x" * 300)
            assert "…" in log[-1][1] and fake.prompts[-1] == "x" * 300
        finally:
            await client.session.close()
            await runner.cleanup()

    run(scenario())
