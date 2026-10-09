# ☁️ CloudHUB

### A Hybrid Self-Hosted Cloud

<img width="400" height="351" alt="CloudHUB-removebg-preview" src="https://github.com/user-attachments/assets/5ecebe41-9061-41e6-bfcb-8501ae880667" />

---

> My private productivity workspace: a self-hosted Nextcloud on AWS EC2, reachable only over Tailscale, with bulk storage on a home TrueNAS SCALE server, a private AI assistant, a Discord bot, and a Terraform rebuild. Zero inbound ports on AWS and none forwarded at home.

![Nextcloud](https://img.shields.io/badge/Nextcloud-0082C9?style=for-the-badge&logo=nextcloud&logoColor=white)
![AWS](https://img.shields.io/badge/AWS_EC2-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu_24.04-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Tailscale](https://img.shields.io/badge/Tailscale-242424?style=for-the-badge&logo=tailscale&logoColor=white)
![TrueNAS](https://img.shields.io/badge/TrueNAS_SCALE-0095D5?style=for-the-badge&logo=truenas&logoColor=white)
![Hyper-V](https://img.shields.io/badge/Hyper--V-0078D4?style=for-the-badge&logo=windows&logoColor=white)
![Terraform](https://img.shields.io/badge/Terraform-844FBA?style=for-the-badge&logo=terraform&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

📄 **Full build report (screenshots, commands, and results):** [`report/CloudHUB-Build-Report.pdf`](report/CloudHUB-Build-Report.pdf)

---

## 📖 Overview

CloudHUB is my private, self-hosted alternative to Google Drive and Microsoft 365: files, documents, calendar, chat, and video calls on infrastructure I control. Nextcloud on EC2 is the single front door, and every connection to it runs through my private Tailscale network.

## 🏗️ Architecture

```
My devices ──(Tailscale, HTTPS via MagicDNS)──► Caddy (Tailscale TLS certs)
                                                  │
                                                  ▼
                                    Nextcloud AIO on AWS EC2 (t3.small)
                                    ├── PostgreSQL · Redis · Office · Talk · Whiteboard
                                    ├── Nextcloud Assistant ──(Tailscale)──► Ollama (llama3.2:3b, home)
                                    ├── External Storage ──(SMB over Tailscale)──► TrueNAS SCALE (home)
                                    └── CloudHUB Discord bot (Docker, outbound only)
```

## ✨ What's in it

| Area | What I built |
|---|---|
| **Cloud front door** | Nextcloud AIO in Docker on EC2 (Ubuntu 24.04), Caddy with auto-renewing Tailscale certificates, Tailscale SSH for admin |
| **Hybrid storage** | TrueNAS SCALE in a Hyper-V VM at home: ZFS pool `tank`, least-privilege SMB share mounted into Nextcloud over Tailscale, daily snapshots |
| **Hardened AWS** | Root MFA, IAM Identity Center (SSO) instead of access keys, $25 budget alert, zero-inbound security group |
| **Infrastructure as Code** | [`terraform/`](terraform/) rebuilds the server with cloud-init (IMDSv2, encrypted EBS, no SSH key), tested end to end and destroyed |
| **Private AI** | Nextcloud Assistant backed by Ollama on my own hardware; a firewall rule lets only the cloud server reach it |
| **Discord bot** | [`discord-bot/`](discord-bot/): `/upload`, `/ask`, `/summarize` (txt, md, PDF, Word), `/status`, and change-only health alerts |
| **Home alerts** | A PowerShell scheduled task posts to Discord when a drive runs low or the NAS VM stops |

## 🔒 Security design

- **Zero public exposure:** no inbound security group rules on AWS and no ports forwarded on the home router; everything runs over Tailscale (WireGuard).
- **Found and fixed a real exposure:** a port scan showed SSH and HTTPS open through a default security group. I removed every rule and confirmed with a rescan.
- **Identity:** root MFA and SSO for AWS, Tailscale SSH instead of key files.
- **Least privilege:** a dedicated SMB user for the NAS, a separate Nextcloud account and app password for the bot, a read-only TrueNAS API key, and the NAS mount visible only to the admin.
- **Hardened containers:** the bot runs as non-root with a read-only filesystem, all capabilities dropped, and no published ports.
- **Secrets stay out of code:** `.env`, `terraform.tfvars`, and the Discord webhook file are git-ignored or locked to Administrators and SYSTEM.

## 📁 Repo layout

| Path | What's there |
|---|---|
| [`report/`](report/) | The full build report PDF: every step with screenshots, commands, results, and a setup reference |
| [`terraform/`](terraform/) | Terraform + cloud-init for the EC2 server |
| [`discord-bot/`](discord-bot/) | The bot, its tests, Docker files, and the home alert script (`surface/`) |
| [`scripts/`](scripts/) | Helper scripts |

## 🚀 Quick start

```bash
# Rebuild the server (uses an SSO profile, not access keys)
aws sso login --profile cloudhub
cd terraform && cp terraform.tfvars.example terraform.tfvars   # add a single-use, ephemeral Tailscale key
terraform init && terraform apply
```

Setup for TrueNAS, Ollama, and the Discord bot is in the [report](report/CloudHUB-Build-Report.pdf) (Appendix) and in [`discord-bot/README.md`](discord-bot/README.md).

## 💡 Lessons learned

- **Verify what you got, not what you planned:** the port scan caught what the console didn't show.
- **Read errors literally:** NXDOMAIN was DNS, and a 502 meant the proxy was up with nothing behind it yet.
- **"Running" isn't healthy:** memory pressure froze the instance while AWS still showed it running.
- **Check where a service listens:** Ollama was bound to `127.0.0.1` until a full restart.
- **Check a secret's shape without printing it:** a 19-digit "token" was really the Application ID.
- **Code keeps the fixes:** Terraform makes zero inbound the default.

## 🗺️ Roadmap

- [x] TrueNAS SCALE storage tier connected over Tailscale
- [x] Hardened AWS rebuild with a zero-inbound security group
- [x] Terraform + cloud-init rebuild
- [x] Nextcloud Assistant backed by a local LLM (Ollama)
- [x] Discord bot with health alerts, plus storage alerts from the home host

## 📊 Monthly cost

| Resource | Cost |
|---|---|
| EC2 t3.small + 30 GB gp3 | ~$17.40 |
| Public IPv4 address | ~$3.60 |
| Data transfer | ~$1–3 |
| Tailscale, TrueNAS, Ollama | $0 (free plans, existing hardware) |
| **Total** | **~$22–24/mo** |
