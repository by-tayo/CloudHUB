"""CloudHUB Discord bot.

Slash commands for a private Nextcloud + Ollama setup:
  /upload     save a Discord attachment into a Nextcloud folder (WebDAV)
  /ask        ask the local Ollama model a question
  /summarize  summarize a text, Markdown, or PDF file stored in Nextcloud
  /status     check EC2 disk and memory, Nextcloud, Ollama, and TrueNAS now

It also checks those every CHECK_INTERVAL_MIN minutes and posts to the
channel only when something breaks or recovers.

Only the user IDs in ALLOWED_USER_IDS can run commands, and only in the
channels listed in CHANNEL_ID or any channel under CATEGORY_ID (if set). The bot holds outbound connections only (Discord
gateway, Nextcloud, Ollama), so no inbound ports are needed.
"""

from __future__ import annotations

import asyncio
import html
import io
import logging
import os
import posixpath
import re
import sys
import zipfile
from urllib.parse import quote, unquote
from xml.etree import ElementTree

import aiohttp
import discord
from discord import app_commands

log = logging.getLogger("cloudhub-bot")

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".log", ".json", ".yaml", ".yml",
    ".ini", ".conf", ".py", ".ps1", ".sh", ".tf", ".html", ".xml",
}
DISCORD_LIMIT = 1900  # stay under Discord's 2,000-character message cap


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


def _int_set(raw: str) -> set[int]:
    return {int(x) for x in raw.replace(" ", "").split(",") if x}


class Config:
    def __init__(self) -> None:
        self.discord_token = _require("DISCORD_TOKEN")
        self.guild_id = int(_require("GUILD_ID"))
        self.allowed_users = _int_set(_require("ALLOWED_USER_IDS"))
        # Where commands are allowed: specific channels and/or a whole category.
        self.channel_ids = _int_set(os.environ.get("CHANNEL_ID", ""))
        category = os.environ.get("CATEGORY_ID", "").strip()
        self.category_id = int(category) if category else None
        # Where alerts are posted (defaults to the first allowed channel).
        alert = os.environ.get("ALERT_CHANNEL_ID", "").strip()
        self.alert_channel_id = int(alert) if alert else next(iter(sorted(self.channel_ids)), None)

        self.nc_url = _require("NC_URL").rstrip("/")
        self.nc_user = _require("NC_USER")
        self.nc_app_password = _require("NC_APP_PASSWORD")
        self.nc_inbox = os.environ.get("NC_INBOX", "Discord Inbox").strip("/")

        self.ollama_url = _require("OLLAMA_URL").rstrip("/")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
        self.ollama_timeout = int(os.environ.get("OLLAMA_TIMEOUT", "240"))

        self.max_upload_mb = int(os.environ.get("MAX_UPLOAD_MB", "25"))
        self.max_summary_chars = int(os.environ.get("MAX_SUMMARY_CHARS", "8000"))

        # Health alerts (all optional; a check is skipped if it isn't configured)
        self.check_interval_min = int(os.environ.get("CHECK_INTERVAL_MIN", "15"))
        self.disk_warn_pct = int(os.environ.get("DISK_WARN_PCT", "85"))
        self.mem_warn_pct = int(os.environ.get("MEM_WARN_PCT", "90"))
        self.disk_probe = os.environ.get("DISK_PROBE_PATH", "/host-root-probe")
        self.meminfo_path = os.environ.get("MEMINFO_PATH", "/proc/meminfo")
        self.truenas_url = os.environ.get("TRUENAS_URL", "").rstrip("/")
        self.truenas_api_key = os.environ.get("TRUENAS_API_KEY", "")
        self.truenas_verify_tls = os.environ.get("TRUENAS_VERIFY_TLS", "false").lower() == "true"
        self.pool_warn_pct = int(os.environ.get("POOL_WARN_PCT", "80"))


# --------------------------------------------------------------------------
# Helpers (pure functions, unit-tested in test_bot.py)
# --------------------------------------------------------------------------


def safe_relpath(path: str) -> str:
    """Normalize a user-supplied Nextcloud path and refuse traversal.

    Returns a path relative to the user's files root with no leading slash.
    Raises ValueError for empty paths or any '..' segment.
    """
    cleaned = (path or "").replace("\\", "/").strip().strip("/")
    if not cleaned:
        raise ValueError("Path is empty.")
    parts = cleaned.split("/")
    if any(p in ("..", ".") for p in parts):
        raise ValueError("Path may not contain '.' or '..' segments.")
    if any(p == "" for p in parts):
        raise ValueError("Path may not contain empty segments ('//').")
    return "/".join(parts)


def safe_filename(name: str) -> str:
    """Keep only the final component of an uploaded file's name."""
    base = posixpath.basename((name or "").replace("\\", "/")).strip()
    if base in ("", ".", ".."):
        raise ValueError("Invalid file name.")
    return base


def dav_url(base: str, user: str, relpath: str) -> str:
    """Build a WebDAV URL with every path segment percent-encoded."""
    encoded = "/".join(quote(seg, safe="") for seg in relpath.split("/") if seg)
    return f"{base}/remote.php/dav/files/{quote(user, safe='')}/{encoded}"


def chunk_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    """Split text into Discord-sized chunks, preferring line breaks."""
    text = text.strip() or "(empty response)"
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    chunks.append(text)
    return chunks


def extract_text(filename: str, data: bytes) -> str:
    """Return readable text from a supported file, or raise ValueError."""
    ext = posixpath.splitext(filename.lower())[1]
    if ext == ".pdf":
        from pypdf import PdfReader  # imported lazily; only needed for PDFs

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        if not text.strip():
            raise ValueError("That PDF has no extractable text (it may be a scan).")
        return text
    if ext == ".docx":
        return docx_text(data)
    if ext in TEXT_EXTENSIONS:
        return data.decode("utf-8", errors="replace")
    raise ValueError(
        f"Unsupported file type '{ext or 'none'}'. "
        "Use a text, Markdown, PDF, or Word (.docx) file."
    )


def docx_text(data: bytes) -> str:
    """Pull the paragraph text out of a .docx (a zip of XML) with the standard library."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > 50 * 1024 * 1024:  # refuse zip bombs
                raise ValueError("That Word file is too large to read.")
            xml = zf.read(info).decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("That doesn't look like a valid Word (.docx) file.") from exc
    xml = re.sub(r"</w:p>|<w:br[^>]*/>|<w:tab[^>]*/>", "\n", xml)
    text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("That Word file has no text.")
    return text


DAV_NS = {"d": "DAV:"}


def parse_propfind(xml_text: str, files_prefix: str) -> list[tuple[str, bool]]:
    """Turn a WebDAV PROPFIND reply into [(relative path, is_folder)].

    files_prefix is the URL path of the user's files root, for example
    /remote.php/dav/files/discord-bot/
    """
    out: list[tuple[str, bool]] = []
    root = ElementTree.fromstring(xml_text)
    for resp in root.findall("d:response", DAV_NS):
        href = unquote(resp.findtext("d:href", default="", namespaces=DAV_NS))
        if not href.startswith(files_prefix):
            continue
        rel = href[len(files_prefix):].strip("/")
        is_folder = resp.find(".//d:resourcetype/d:collection", DAV_NS) is not None
        if rel:
            out.append((rel, is_folder))
    return out


# --------------------------------------------------------------------------
# Nextcloud and Ollama clients
# --------------------------------------------------------------------------


class Nextcloud:
    def __init__(self, cfg: Config, session: aiohttp.ClientSession) -> None:
        self.cfg = cfg
        self.session = session
        self.auth = aiohttp.BasicAuth(cfg.nc_user, cfg.nc_app_password)

    async def ensure_folder(self, relpath: str) -> None:
        """Create each folder level if missing (MKCOL)."""
        current = ""
        for part in relpath.split("/"):
            current = f"{current}/{part}" if current else part
            async with self.session.request(
                "MKCOL", dav_url(self.cfg.nc_url, self.cfg.nc_user, current), auth=self.auth
            ) as resp:
                # 201 created, 405 already exists
                if resp.status not in (201, 405):
                    raise RuntimeError(f"Could not create folder '{current}' (HTTP {resp.status}).")

    async def exists(self, relpath: str) -> bool:
        async with self.session.request(
            "PROPFIND",
            dav_url(self.cfg.nc_url, self.cfg.nc_user, relpath),
            auth=self.auth,
            headers={"Depth": "0"},
        ) as resp:
            return resp.status == 207

    async def put(self, relpath: str, data: bytes) -> None:
        async with self.session.put(
            dav_url(self.cfg.nc_url, self.cfg.nc_user, relpath), data=data, auth=self.auth
        ) as resp:
            if resp.status not in (201, 204):
                raise RuntimeError(f"Upload failed (HTTP {resp.status}).")

    async def list_folder(self, relpath: str) -> list[tuple[str, bool]]:
        """One level of a folder: [(relative path, is_folder)], the folder itself left out."""
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
        async with self.session.request(
            "PROPFIND",
            dav_url(self.cfg.nc_url, self.cfg.nc_user, relpath),
            auth=self.auth,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=body,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 207:
                return []
            text = await resp.text()
        prefix = f"/remote.php/dav/files/{self.cfg.nc_user}/"
        return [(p, f) for p, f in parse_propfind(text, prefix) if p != relpath.strip("/")]

    async def list_files(self, relpath: str, max_folders: int = 10) -> list[str]:
        """Files in a folder and one level of its subfolders."""
        files: list[str] = []
        folders: list[str] = []
        for path, is_folder in await self.list_folder(relpath):
            (folders if is_folder else files).append(path)
        for sub in folders[:max_folders]:
            files.extend(p for p, is_folder in await self.list_folder(sub) if not is_folder)
        return sorted(files, key=str.lower)

    async def get(self, relpath: str, max_bytes: int) -> bytes:
        async with self.session.get(
            dav_url(self.cfg.nc_url, self.cfg.nc_user, relpath), auth=self.auth
        ) as resp:
            if resp.status == 404:
                raise ValueError("File not found. Check the path (it's relative to the bot user's files).")
            if resp.status != 200:
                raise RuntimeError(f"Download failed (HTTP {resp.status}).")
            data = await resp.content.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError(f"File is larger than {max_bytes // (1024 * 1024)} MB.")
            return data


class Ollama:
    def __init__(self, cfg: Config, session: aiohttp.ClientSession) -> None:
        self.cfg = cfg
        self.session = session

    async def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.cfg.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        timeout = aiohttp.ClientTimeout(total=self.cfg.ollama_timeout)
        try:
            async with self.session.post(
                f"{self.cfg.ollama_url}/chat/completions", json=payload, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Ollama returned HTTP {resp.status}.")
                body = await resp.json()
        except aiohttp.ClientConnectorError as exc:
            raise RuntimeError(
                "Can't reach Ollama. Is the Surface awake and on Tailscale?"
            ) from exc
        return body["choices"][0]["message"]["content"]


# --------------------------------------------------------------------------
# Health checks (for /status and the alert loop)
# --------------------------------------------------------------------------

# A check result: (key, ok, detail). Keys are stable so alerts can track
# state changes and only post when something breaks or recovers.
Check = tuple[str, bool, str]


def parse_meminfo(text: str) -> dict[str, int]:
    """Parse /proc/meminfo into {field: kB}."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            out[name.strip()] = int(parts[0])
    return out


def pct(used: float, total: float) -> int:
    return round(100 * used / total) if total else 0


def check_disk(cfg: Config) -> Check:
    try:
        st = os.statvfs(cfg.disk_probe)
    except OSError:
        return ("ec2-disk", True, "EC2 disk: not checked (probe path not mounted)")
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used_pct = pct(total - free, total)
    detail = f"EC2 disk: {used_pct}% used ({free / 1e9:.1f} GB free of {total / 1e9:.1f} GB)"
    return ("ec2-disk", used_pct < cfg.disk_warn_pct, detail)


def check_memory(cfg: Config) -> Check:
    try:
        with open(cfg.meminfo_path) as fh:
            info = parse_meminfo(fh.read())
    except OSError:
        return ("ec2-memory", True, "EC2 memory: not checked")
    total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
    used_pct = pct(total - avail, total)
    swap_total, swap_free = info.get("SwapTotal", 0), info.get("SwapFree", 0)
    swap = f", swap {pct(swap_total - swap_free, swap_total)}% used" if swap_total else ""
    detail = f"EC2 memory: {used_pct}% used ({avail / 1e6:.2f} GB available){swap}"
    return ("ec2-memory", used_pct < cfg.mem_warn_pct, detail)


async def check_url(session: aiohttp.ClientSession, key: str, label: str, url: str, **kw) -> Check:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), **kw) as resp:
            ok = resp.status == 200
            return (key, ok, f"{label}: {'reachable' if ok else f'HTTP {resp.status}'}")
    except (aiohttp.ClientError, TimeoutError):
        return (key, False, f"{label}: unreachable")


async def check_truenas(cfg: Config, session: aiohttp.ClientSession) -> list[Check]:
    """Pool health and capacity, plus TrueNAS's own active alerts."""
    if not (cfg.truenas_url and cfg.truenas_api_key):
        return []
    headers = {"Authorization": f"Bearer {cfg.truenas_api_key}"}
    ssl = None if cfg.truenas_verify_tls else False
    timeout = aiohttp.ClientTimeout(total=20)
    results: list[Check] = []
    try:
        async with session.get(f"{cfg.truenas_url}/api/v2.0/pool", headers=headers, ssl=ssl, timeout=timeout) as resp:
            if resp.status != 200:
                return [("truenas", False, f"TrueNAS: API returned HTTP {resp.status}")]
            pools = await resp.json()
        async with session.get(f"{cfg.truenas_url}/api/v2.0/alert/list", headers=headers, ssl=ssl, timeout=timeout) as resp:
            alerts = await resp.json() if resp.status == 200 else []
    except (aiohttp.ClientError, TimeoutError):
        return [("truenas", False, "TrueNAS: unreachable (is the Surface awake and the VM running?)")]

    for pool in pools:
        name = pool.get("name", "?")
        healthy = bool(pool.get("healthy")) and pool.get("status") == "ONLINE"
        size, allocated = pool.get("size") or 0, pool.get("allocated") or 0
        usage = f", {pct(allocated, size)}% used" if size else ""
        results.append((f"pool-{name}-health", healthy, f"Pool {name}: {pool.get('status', '?')}{usage}"))
        if size:
            results.append((
                f"pool-{name}-capacity",
                pct(allocated, size) < cfg.pool_warn_pct,
                f"Pool {name} capacity: {pct(allocated, size)}% used",
            ))

    active = [a for a in alerts if not a.get("dismissed") and a.get("level") in ("WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY")]
    if active:
        lines = "; ".join((a.get("formatted") or a.get("klass") or "alert").strip()[:150] for a in active[:3])
        more = f" (+{len(active) - 3} more)" if len(active) > 3 else ""
        results.append(("truenas-alerts", False, f"TrueNAS alerts: {lines}{more}"))
    else:
        results.append(("truenas-alerts", True, "TrueNAS alerts: none"))
    return results


async def run_checks(bot: "CloudHubBot") -> list[Check]:
    assert bot.session is not None
    cfg = bot.cfg
    checks: list[Check] = [check_disk(cfg), check_memory(cfg)]
    checks.append(await check_url(bot.session, "nextcloud", "Nextcloud", f"{cfg.nc_url}/status.php"))
    checks.append(await check_url(bot.session, "ollama", "Ollama on the Surface", f"{cfg.ollama_url}/models"))
    checks.extend(await check_truenas(cfg, bot.session))
    return checks


def diff_alerts(previous: dict[str, bool], checks: list[Check]) -> list[str]:
    """Messages for checks whose state changed. First run reports only problems."""
    messages = []
    for key, ok, detail in checks:
        before = previous.get(key)
        if before is None and not ok:
            messages.append(f"⚠️ {detail}")
        elif before is True and not ok:
            messages.append(f"⚠️ {detail}")
        elif before is False and ok:
            messages.append(f"✅ Recovered: {detail}")
        previous[key] = ok
    return messages


# --------------------------------------------------------------------------
# Bot
# --------------------------------------------------------------------------


class CloudHubBot(discord.Client):
    def __init__(self, cfg: Config) -> None:
        # Default intents only: slash commands don't need message content.
        super().__init__(intents=discord.Intents.default())
        self.cfg = cfg
        self.tree = app_commands.CommandTree(self)
        self.session: aiohttp.ClientSession | None = None
        self.nc: Nextcloud | None = None
        self.ollama: Ollama | None = None
        self.alert_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()
        self.nc = Nextcloud(self.cfg, self.session)
        self.ollama = Ollama(self.cfg, self.session)
        guild = discord.Object(id=self.cfg.guild_id)
        register_commands(self)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Synced %d commands to guild %s", len(synced), self.cfg.guild_id)
        if self.cfg.alert_channel_id and self.cfg.check_interval_min > 0:
            self.alert_task = asyncio.create_task(self.alert_loop())

    async def alert_loop(self) -> None:
        """Every CHECK_INTERVAL_MIN, post to the channel when a check breaks or recovers."""
        await self.wait_until_ready()
        state: dict[str, bool] = {}
        while not self.is_closed():
            try:
                messages = diff_alerts(state, await run_checks(self))
                if messages:
                    cid = self.cfg.alert_channel_id
                    channel = self.get_channel(cid) or await self.fetch_channel(cid)
                    for chunk in chunk_message("\n".join(messages)):
                        await channel.send(chunk)
            except Exception:  # keep the loop alive no matter what one run hits
                log.exception("Alert check failed")
            await asyncio.sleep(self.cfg.check_interval_min * 60)

    async def close(self) -> None:
        if self.alert_task:
            self.alert_task.cancel()
        if self.session:
            await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Logged in as %s (id %s)", self.user, self.user.id if self.user else "?")


async def _authorized(bot: CloudHubBot, interaction: discord.Interaction) -> bool:
    if interaction.user.id not in bot.cfg.allowed_users:
        await interaction.response.send_message("You're not allowed to use this bot.", ephemeral=True)
        return False
    if not channel_allowed(bot.cfg, interaction):
        where = " or ".join(
            [f"<#{c}>" for c in sorted(bot.cfg.channel_ids)]
            + (["a channel in the CloudHUB category"] if bot.cfg.category_id else [])
        )
        await interaction.response.send_message(f"Use this in {where}.", ephemeral=True)
        return False
    return True


def channel_allowed(cfg: Config, interaction: discord.Interaction) -> bool:
    """True if no channel limits are set, the channel is listed, or it sits in CATEGORY_ID."""
    if not cfg.channel_ids and not cfg.category_id:
        return True
    if interaction.channel_id in cfg.channel_ids:
        return True
    if cfg.category_id:
        channel = getattr(interaction, "channel", None)
        category = getattr(channel, "category_id", None)
        if category is None:  # threads: use the parent channel's category
            category = getattr(getattr(channel, "parent", None), "category_id", None)
        return category == cfg.category_id
    return False


async def _send_chunks(interaction: discord.Interaction, header: str, text: str) -> None:
    chunks = chunk_message(text, DISCORD_LIMIT - len(header) - 2)
    await interaction.followup.send(f"{header}\n{chunks[0]}")
    for extra in chunks[1:]:
        await interaction.followup.send(extra)


def register_commands(bot: CloudHubBot) -> None:
    tree = bot.tree

    @tree.command(name="upload", description="Save a file to your Nextcloud inbox folder")
    @app_commands.describe(file="The file to save", folder="Subfolder inside the inbox (optional)")
    async def upload(interaction: discord.Interaction, file: discord.Attachment, folder: str | None = None) -> None:
        if not await _authorized(bot, interaction):
            return
        max_bytes = bot.cfg.max_upload_mb * 1024 * 1024
        if file.size > max_bytes:
            await interaction.response.send_message(
                f"That file is over {bot.cfg.max_upload_mb} MB.", ephemeral=True
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            name = safe_filename(file.filename)
            target_dir = bot.cfg.nc_inbox + (f"/{safe_relpath(folder)}" if folder else "")
            target = f"{target_dir}/{name}"
            assert bot.nc is not None
            await bot.nc.ensure_folder(target_dir)
            if await bot.nc.exists(target):
                stem, ext = posixpath.splitext(name)
                target = f"{target_dir}/{stem}-{interaction.id}{ext}"
            await bot.nc.put(target, await file.read())
        except (ValueError, RuntimeError) as exc:
            await interaction.followup.send(f"❌ {exc}")
            return
        await interaction.followup.send(f"✅ Saved to Nextcloud: `{target}`")

    @tree.command(name="ask", description="Ask the private Ollama model a question")
    @app_commands.describe(prompt="Your question")
    async def ask(interaction: discord.Interaction, prompt: app_commands.Range[str, 1, 1500]) -> None:
        if not await _authorized(bot, interaction):
            return
        await interaction.response.defer(thinking=True)
        try:
            assert bot.ollama is not None
            answer = await bot.ollama.chat(
                "You are a concise, helpful assistant. Answer in plain text.", prompt
            )
        except (RuntimeError, KeyError, aiohttp.ClientError, TimeoutError) as exc:
            await interaction.followup.send(f"❌ {exc or 'Ollama request failed or timed out.'}")
            return
        shown = prompt if len(prompt) <= 200 else prompt[:199] + "…"
        await _send_chunks(interaction, f"**Q:** {shown}", answer)

    async def inbox_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.user.id not in bot.cfg.allowed_users or bot.nc is None:
            return []
        try:
            files = await bot.nc.list_files(bot.cfg.nc_inbox)
        except (aiohttp.ClientError, TimeoutError, ElementTree.ParseError):
            return []
        needle = current.lower()
        matches = [f for f in files if needle in f.lower() and len(f) <= 100]
        return [app_commands.Choice(name=f, value=f) for f in matches[:25]]

    @tree.command(name="summarize", description="Summarize a text, Markdown, PDF, or Word file from Nextcloud")
    @app_commands.describe(path="Start typing to pick a file from your Discord Inbox")
    @app_commands.autocomplete(path=inbox_autocomplete)
    async def summarize(interaction: discord.Interaction, path: str) -> None:
        if not await _authorized(bot, interaction):
            return
        await interaction.response.defer(thinking=True)
        try:
            rel = safe_relpath(path)
            assert bot.nc is not None and bot.ollama is not None
            data = await bot.nc.get(rel, bot.cfg.max_upload_mb * 1024 * 1024)
            text = extract_text(rel, data)
            truncated = len(text) > bot.cfg.max_summary_chars
            text = text[: bot.cfg.max_summary_chars]
            summary = await bot.ollama.chat(
                "Summarize the document in 5-8 bullet points, then one line of key takeaways. "
                "Use plain text.",
                text,
            )
        except (ValueError, RuntimeError, KeyError, aiohttp.ClientError, TimeoutError) as exc:
            await interaction.followup.send(f"❌ {exc or 'Request failed or timed out.'}")
            return
        note = " (first part only; the file was long)" if truncated else ""
        await _send_chunks(interaction, f"**Summary of** `{rel}`{note}", summary)

    @tree.command(name="status", description="Check EC2, Nextcloud, Ollama, and TrueNAS right now")
    async def status(interaction: discord.Interaction) -> None:
        if not await _authorized(bot, interaction):
            return
        await interaction.response.defer(thinking=True)
        checks = await run_checks(bot)
        lines = [f"{'🟢' if ok else '🔴'} {detail}" for _, ok, detail in checks]
        await _send_chunks(interaction, "**CloudHUB status**", "\n".join(lines))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config()
    CloudHubBot(cfg).run(cfg.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
