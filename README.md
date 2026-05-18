# ☁️ CloudHUB


<img width="400" height="351" alt="CloudHUB-removebg-preview" src="https://github.com/user-attachments/assets/5ecebe41-9061-41e6-bfcb-8501ae880667" />





---

> My personal productivity workspace — a self-hosted Nextcloud instance running on AWS EC2, secured with Tailscale VPN and deployed via Docker.

![Nextcloud](https://img.shields.io/badge/Nextcloud-0082C9?style=for-the-badge&logo=nextcloud&logoColor=white)
![AWS](https://img.shields.io/badge/AWS_EC2-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu_24.04-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Tailscale](https://img.shields.io/badge/Tailscale-242424?style=for-the-badge&logo=tailscale&logoColor=white)

---

## 📖 Overview

CloudHUB is what I call my personal Nextcloud instance — my private, self-hosted alternative to Google Drive, Microsoft 365, and other third-party productivity platforms. Rather than relying on external cloud providers, CloudHUB gives me full ownership and control over my files, documents, calendar, and communications.

It runs on AWS EC2, is accessible only through Tailscale VPN, and serves as my central hub for all productivity work — from writing and file management to video calls and collaborative documents.

---

## 🏗️ Architecture

```
Client Device (Tailscale VPN)
        │
        ▼ HTTPS via Magic DNS
Caddy Reverse Proxy (TLS termination)
        │
        ▼ Port 11000
Nextcloud AIO Master Container
        │
        ├── Nextcloud (v33.0.3)
        ├── PostgreSQL (Database)
        ├── Redis (Caching)
        ├── Nextcloud Office (LibreOffice-based)
        ├── Nextcloud Talk (Video/Chat)
        ├── Imaginary (Image Processing)
        └── Nextcloud Whiteboard
```

---

## 🛠️ Tech Stack

### Infrastructure
| Component | Technology |
|---|---|
| Cloud Provider | AWS EC2 (t3.small, us-east-1) |
| OS | Ubuntu Server 24.04 LTS |
| Storage | 30 GB gp3 EBS Volume |
| Static IP | AWS Elastic IP |

### Networking & Security
| Component | Technology |
|---|---|
| VPN | Tailscale (WireGuard-based) |
| DNS | Tailscale Magic DNS |
| TLS/HTTPS | Tailscale Certificates |
| Reverse Proxy | Caddy v2 |
| Firewall | AWS Security Groups |
| Access Control | Private Tailnet (invite-only) |

### Application Stack
| Component | Technology |
|---|---|
| Platform | Nextcloud Hub v33.0.3 |
| Deployment | Nextcloud AIO (All-in-One) v13 |
| Containerization | Docker Engine v29.5.0 |
| Database | PostgreSQL (via AIO) |
| Caching | Redis (via AIO) |
| Web Server | Apache (via AIO) |
| Office Suite | Nextcloud Office (LibreOffice) |
| Communication | Nextcloud Talk |
| Image Processing | Imaginary |
| Collaboration | Nextcloud Whiteboard |

---

## 🔒 Security Design

- **Zero public exposure** — CloudHUB is not accessible from the public internet
- **VPN-only access** — all traffic routes through Tailscale's encrypted WireGuard tunnel
- **TLS encryption** — end-to-end HTTPS via Tailscale-issued certificates
- **AWS Security Groups** — SSH restricted to admin IP; ports locked down
- **AIO Reverse Proxy Mode** — Caddy handles TLS termination, Nextcloud never directly exposed
- **Private Magic DNS** — domain only resolvable inside the Tailscale network

---

## 🚀 Deployment

### Prerequisites
- AWS account with EC2 access
- Tailscale account
- Ubuntu 24.04 LTS EC2 instance (t3.small minimum)
- Docker Engine installed


### SSH Into the Instance

```bash
ssh -i ~/.ssh/[your-key].pem ubuntu@[your-ec2-ip]
```

```bash
# Update system
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget
sudo reboot
```

ℹ️ After reboot, reconnect using the same SSH command.




### Quick Start

**1. Install Docker:**
```bash
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
```

**2. Install and configure Tailscale:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale cert your-machine.tail1234ab.ts.net
```

**3. Configure Caddy:**
```
your-machine.tail1234ab.ts.net {
    reverse_proxy localhost:11000
    tls /var/lib/tailscale/certs/your-machine.tail1234ab.ts.net.crt \
        /var/lib/tailscale/certs/your-machine.tail1234ab.ts.net.key
}
```

**4. Run Nextcloud AIO:**
```bash
docker run \
  --sig-proxy=false \
  --name nextcloud-aio-mastercontainer \
  --restart always \
  --publish 8080:8080 \
  --env APACHE_PORT=11000 \
  --env APACHE_IP_BINDING=127.0.0.1 \
  --env SKIP_DOMAIN_VALIDATION=true \
  --volume nextcloud_aio_mastercontainer:/mnt/docker-aio-config \
  --volume /var/run/docker.sock:/var/run/docker.sock:ro \
  nextcloud/all-in-one:latest
```

---

## 💡 What I Use CloudHUB For

- 📁 **File Storage** — my personal alternative to Google Drive
- 📝 **Documents & Spreadsheets** — real-time editing via Nextcloud Office
- 💬 **Video Calls & Chat** — private communication via Nextcloud Talk
- 📅 **Calendar & Contacts** — all in one place, no Google required
- 🖼️ **Whiteboard** — brainstorming and visual planning
- 🔒 **Full Data Ownership** — everything stays on infrastructure I control

---

## 📊 Infrastructure Cost

| Resource | Monthly Cost |
|---|---|
| EC2 t3.small | ~$15.00 |
| EBS 30GB gp3 | ~$2.40 |
| Elastic IP | $0.00 (attached) |
| Data Transfer | ~$1–3.00 |
| Tailscale | $0.00 (free plan) |
| **Total** | **~$18–20/mo** |

---
