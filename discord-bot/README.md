# 🤖 CloudHUB Discord Bot

A small Python bot for the **#CloudHUB** Discord channel. It runs in Docker on the CloudHUB EC2 instance, talks to Nextcloud and the local Ollama model over Tailscale, and only makes **outbound** connections, so the security group stays at zero inbound rules.

| Command | What it does |
|---|---|
| `/upload file [folder]` | Saves a Discord attachment into the `Discord Inbox` folder in Nextcloud |
| `/ask prompt` | Asks the private Ollama model (`llama3.2:3b` on the Surface) |
| `/summarize path` | Pulls a text, Markdown, PDF, or Word (.docx) file from Nextcloud and summarizes it with Ollama (file names autocomplete from your inbox) |
| `/status` | Checks EC2 disk and memory, Nextcloud, Ollama, and the TrueNAS pool and alerts right now |

**Automatic alerts:** every 15 minutes the bot runs the same checks as `/status` and posts in the alert channel **only when something breaks or recovers**. For example, EC2 disk over 85%, the pool over 80%, a TrueNAS warning, or the Surface going offline.

**Surface alerts:** EC2 can't see the laptop's own drives, so `surface/Watch-SurfaceHealth.ps1` runs on the Surface as a scheduled task. It posts to the same channel through a webhook when a drive gets low or the TrueNAS VM stops.

## Security design

- **Who can run commands:** only the user IDs in `ALLOWED_USER_IDS`, and only in channels under `CATEGORY_ID` (or the channels listed in `CHANNEL_ID`).
- **No privileged Discord intents:** slash commands don't need permission to read messages.
- **Dedicated Nextcloud account:** the bot logs in as its own `discord-bot` user with an **app password**. It only sees folders you share with it.
- **Read-only TrueNAS key:** the API key belongs to a read-only user.
- **Safe paths:** path traversal (`..`) is rejected, and uploads never overwrite an existing file.
- **Locked-down container:** non-root user, read-only filesystem, all Linux capabilities dropped, a 128 MB memory cap, and no published ports. The disk check reads free space from one empty folder and never sees the host's files.
- **Trade-off:** anything the bot posts (answers, summaries, alerts) is stored on Discord's servers. Keep sensitive documents in the Nextcloud Assistant.

## Files

| File | Purpose |
|---|---|
| `bot.py` | The bot |
| `test_bot.py` | Offline tests against a fake Nextcloud, Ollama, and TrueNAS (`python -m pytest -q`) |
| `requirements.txt` | Pinned dependencies (discord.py, aiohttp, pypdf) |
| `Dockerfile`, `docker-compose.yml` | Hardened container |
| `.env.example` | Copy to `.env` (git-ignored) and fill in |
| `surface/Watch-SurfaceHealth.ps1` | Surface drive and VM checks, posting through a webhook |

## Setup

### 1. Create the Discord bot
1. Go to <https://discord.com/developers/applications> → **New Application** → name it `CloudHUB`.
2. **Bot** tab → **Reset Token** → copy it (this is `DISCORD_TOKEN`). Leave all *Privileged Gateway Intents* **off**.
3. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; bot permissions **View Channels** + **Send Messages**. Open the URL and add the bot to your server.
4. In Discord: **User Settings → Advanced → Developer Mode** on. Then right-click to **Copy ID** for your server (`GUILD_ID`), your profile (`ALLOWED_USER_IDS`), the CloudHUB category (`CATEGORY_ID`), and the channel that should receive alerts (`ALERT_CHANNEL_ID`).

### 2. Create the Nextcloud bot account (on EC2)
```bash
sudo docker exec -it --user www-data nextcloud-aio-nextcloud \
  php occ user:add --display-name="Discord Bot" discord-bot
```
Then:
1. **As admin**, create a folder named `Discord Inbox` and share it with `discord-bot` with **edit** rights. Uploads land in *your* files.
2. Log in as `discord-bot` in a private window → **Settings → Security → Create new app password** → copy it (`NC_APP_PASSWORD`).

### 3. Optional: a read-only TrueNAS API key
In TrueNAS, create a user (for example `discord-bot-ro`) with the **Read-Only Administrator** role. Then create an API key for that user from the account menu → **API Keys**. Set `TRUENAS_URL=https://<truenas-tailscale-ip>`. TrueNAS revokes API keys that are used over plain HTTP, so keep it on HTTPS.

### 4. Deploy on EC2
```bash
# from your laptop, in the folder that contains discord-bot/
scp -r discord-bot cloudhub:~/

# on EC2
ssh cloudhub
sudo mkdir -p /opt/cloudhub-bot/probe
cd ~/discord-bot
cp .env.example .env && nano .env      # fill in every value
chmod 600 .env
sudo docker compose up -d --build
sudo docker logs -f cloudhub-bot       # expect "Synced 4 commands" and "Logged in as CloudHUB"
```
Ollama already allows the EC2 Tailscale IP through the Surface firewall, so nothing changes there.

### 5. Test it in #CloudHUB
`/status` → `/ask prompt: what is ZFS?` → `/upload` a small `.md` file → `/summarize path: Discord Inbox/<file>.md`

### 6. Surface alerts (Administrator PowerShell on the Surface)
1. In Discord: **#CloudHUB → Edit Channel → Integrations → Webhooks → New Webhook** → copy the URL.
2. Save the webhook URL where only Administrators and SYSTEM can read it:
```powershell
$dir = "$env:ProgramData\CloudHUB"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
Set-Content "$dir\webhook.txt" "PASTE-WEBHOOK-URL-HERE"
icacls $dir /inheritance:r /grant:r "Administrators:(OI)(CI)F" "SYSTEM:(OI)(CI)F" | Out-Null
Copy-Item .\surface\Watch-SurfaceHealth.ps1 "$dir\Watch-SurfaceHealth.ps1"
& "$dir\Watch-SurfaceHealth.ps1" -Test     # a test message should appear in #CloudHUB
```
3. Run it every 30 minutes as SYSTEM:
```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$env:ProgramData\CloudHUB\Watch-SurfaceHealth.ps1`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "CloudHUB Surface Health" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest
```

## Limits
- `/ask` and `/summarize` need the Surface awake. If it isn't, the bot says so instead of hanging.
- `/summarize` reads the first 8,000 characters (`MAX_SUMMARY_CHARS`), because a small model has a limited context window. Scanned PDFs without a text layer can't be summarized.
- The TrueNAS checks use the REST API (`/api/v2.0`), which TrueNAS has marked as deprecated in favor of its JSON-RPC API. It works on 25.10, but a future TrueNAS release may need an update.
