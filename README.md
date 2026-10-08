# ☁️ CloudHUB — Hybrid Self-Hosted Cloud


<img width="400" height="351" alt="CloudHUB-removebg-preview" src="https://github.com/user-attachments/assets/5ecebe41-9061-41e6-bfcb-8501ae880667" />





---

> My personal productivity workspace a self-hosted Nextcloud instance running on AWS EC2, secured with Tailscale VPN and deployed via Docker. Now expanding into a hybrid setup, with bulk storage on a home TrueNAS SCALE server reached over the same tailnet.

![Nextcloud](https://img.shields.io/badge/Nextcloud-0082C9?style=for-the-badge&logo=nextcloud&logoColor=white)
![AWS](https://img.shields.io/badge/AWS_EC2-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Ubuntu](https://img.shields.io/badge/Ubuntu_24.04-E95420?style=for-the-badge&logo=ubuntu&logoColor=white)
![Tailscale](https://img.shields.io/badge/Tailscale-242424?style=for-the-badge&logo=tailscale&logoColor=white)
![TrueNAS](https://img.shields.io/badge/TrueNAS_SCALE-0095D5?style=for-the-badge&logo=truenas&logoColor=white)
![Hyper-V](https://img.shields.io/badge/Hyper--V-0078D4?style=for-the-badge&logo=windows&logoColor=white)

---

## 📖 Overview

CloudHUB is what I call my personal Nextcloud instance my private, self-hosted alternative to Google Drive, Microsoft 365, and other third-party productivity platforms. Rather than relying on external cloud providers, CloudHUB gives me full ownership and control over my files, documents, calendar, and communications.

It runs on AWS EC2, is accessible only through Tailscale VPN, and serves as my central hub for all productivity work — from writing and file management to video calls and collaborative documents.

**What's new:** the EC2 instance runs on a 30 GB EBS volume, so I'm adding a home **TrueNAS SCALE** server as a second storage tier. Nextcloud on EC2 stays the single front door; the TrueNAS share is mounted into it as external storage over Tailscale, so nothing on my home network is exposed to the internet.

> **Status (Oct 2026):** after closing my original AWS account, I rebuilt CloudHUB on a new hardened account (root MFA, an IAM Identity Center admin login, and a $25 monthly budget alert) in us-east-2. Nextcloud on EC2 now mounts the home TrueNAS share over Tailscale, verified with reads and writes in both directions. See the **Roadmap** for what's next.

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
        ├── Nextcloud Whiteboard
        └── External Storage app ──── SMB over Tailscale (TCP 445) ────┐
                                                                       │
                                                                       ▼
                                          Home: Surface Book 3 (Windows 11 Pro, Hyper-V)
                                                                       │
                                                                       ▼
                                                     TrueNAS SCALE VM (Community Edition 25.10)
                                                       ├── Tailscale app (host network)
                                                       ├── ZFS pool: tank
                                                       └── Dataset tank/cloudhub → SMB share "cloudhub"
```

## 🛠️ Tech Stack

### Infrastructure
| Component | Technology |
|---|---|
| Cloud Provider | AWS EC2 (t3.small, us-east-2) |
| OS | Ubuntu Server 24.04 LTS |
| Storage | 30 GB gp3 EBS Volume |
| Public IP | Auto-assigned public IPv4 (no Elastic IP; admin access via Tailscale) |

### Home Storage Tier
| Component | Technology |
|---|---|
| Host | Microsoft Surface Book 3 (Intel i7-1065G7, 32 GB RAM, 1 TB SSD) |
| Hypervisor | Hyper-V on Windows 11 Pro (Generation 2 VM, Default Switch) |
| NAS OS | TrueNAS SCALE / Community Edition 25.10.7 |
| VM Resources | 16 GB fixed RAM, 4 vCPUs |
| Disks | 32 GB boot VHDX + 64 GB dynamic data VHDX |
| Filesystem | ZFS — pool `tank`, dataset `tank/cloudhub` |
| File Sharing | SMB share `cloudhub` |
| Remote Access | Tailscale app (community train), host network, userspace off |

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
- **AWS Security Groups** — zero inbound rules; SSH and HTTPS reach the instance only over Tailscale
- **AIO Reverse Proxy Mode** — Caddy handles TLS termination, Nextcloud never directly exposed
- **Private Magic DNS** — domain only resolvable inside the Tailscale network
- **NAS reachable only over the tailnet** — the TrueNAS SMB share is reached at its Tailscale address; no ports are forwarded on the home router
- **Least-privilege SMB account** — Nextcloud connects as a dedicated `nextcloud-smb` user with SMB access only (no shell, no TrueNAS admin access, no API keys) and Modify rights on the one dataset it needs

---

## 🧱 Hybrid Storage: TrueNAS SCALE

Nextcloud on EC2 stays the single entry point, while bulk files live on ZFS storage at home. The TrueNAS share is mounted in Nextcloud as `/TrueNAS`, and I tested reads and writes in both directions.

### Why a VM on a laptop?
My main machine didn't have the free space, so I repurposed a Surface Book 3. It has no Ethernet port (and TrueNAS doesn't support Wi-Fi) and only one internal drive, so instead of installing TrueNAS on the bare metal I run it as a **Hyper-V VM**. The VM uses Hyper-V's Default Switch for outbound internet; once Tailscale runs inside TrueNAS, everything else reaches it at its tailnet address.

### Build log
| Phase | Step | Status |
|---|---|---|
| 0 | Prepare host (no sleep while plugged in, lid does nothing), confirm Hyper-V | ✅ Done |
| 0 | Create VM with a defensive PowerShell script (checks ISO, name clash, switch, free disk space) | ✅ Done |
| 0 | Install TrueNAS 25.10.7, create ZFS pool `tank` (single-disk stripe — lab only) | ✅ Done |
| 1 | Install the Tailscale app (host network on, userspace off) and join the tailnet | ✅ Done |
| 2 | Create dataset `tank/cloudhub` with the SMB preset | ✅ Done |
| 3 | Create `nextcloud-smb` user and grant Modify on the dataset ACL | ✅ Done |
| 4 | Enable the `cloudhub` SMB share and SMB service; write a test file | ✅ Done |
| 5 | Confirm EC2 reaches TrueNAS over Tailscale on TCP 445 | ✅ Done |
| 6 | Mount the share in Nextcloud via External Storage (SMB/CIFS) | ✅ Done |
| 7 | Harden: daily ZFS snapshots (2-week retention), remove `builtin_users` from the dataset ACL, restrict the Nextcloud mount to the admin account | ✅ Done |

### Lessons
- **The pre-flight checks paid off.** The VM script refused to run on the first attempt because the host only had 131 GB free — not enough for the planned 256 GB data disk plus margin. Dropping the data disk to 64 GB (dynamic, so it only grows as it fills) fixed it before anything was created.
- **Tailscale needs host networking for this use case.** The TrueNAS Tailscale app's default (userspace) mode suits reaching the web UI, but Nextcloud needs to reach the SMB service on the TrueNAS host itself so the app runs with host network enabled and userspace disabled.
- **If the NAS drops off the tailnet, restart the app first.** The app showed Running while the machine showed offline in the Tailscale console; a restart reconnected it.

- **Caddy can manage Tailscale certificates itself.** Setting `TS_PERMIT_CERT_UID=caddy` lets Caddy fetch and auto-renew the `*.ts.net` certificate, replacing the manual `tailscale cert` step that expires every ~90 days.
- **"Site can't be reached" was DNS, not the server.** `DNS_PROBE_FINISHED_NXDOMAIN` meant the laptop wasn't on the tailnet; once it was, MagicDNS resolved the name and Caddy answered.
- **Tailscale SSH removes the dependency on port 22 and key files.** `tailscale up --ssh` let me reach the instance as `ssh ubuntu@cloudhub` even when its public IP changed.

- **Verify the security group you actually got.** A port scan of the public IP showed 22 and 443 open: the instance had been launched with the wizard's default group, not the planned one. After removing both rules, a rescan showed 22, 80, 443, 8080, and 8443 all closed, while Nextcloud and SSH kept working over Tailscale.

- **"Running" in AWS doesn't mean responsive.** After the security group change, the instance still showed Running but stopped answering over Tailscale. A reboot brought it back; `free -h` then showed 1.6 GB of 1.9 GB in use right after boot, so the t3.small's 2 GB RAM is tight for Nextcloud AIO. Restarting the containers brought it to 1.1 GB used with 2 GB swap as a buffer; turning off Office/Talk or moving to a t3.medium are the next levers.
- **Least privilege on both ends.** The TrueNAS dataset ACL now grants write access only to `nextcloud-smb` (the default `builtin_users` entry was removed), and the Nextcloud mount is visible only to the admin account.
- **Rebuilding from code fixes the mistakes by design.** A Terraform test deploy (`cloudhub-tf`) came up with zero inbound rules on its own: the security group check returned `[]`, so the wizard-default problem above can't recur. With no manual steps, cloud-init finished with swap, Docker, Tailscale SSH, Caddy and its certificate, and the AIO master container, and the box joined the tailnet. The 502 on the new URL was expected, since Nextcloud only listens once the AIO setup has run. Terraform authenticates through an IAM Identity Center (SSO) profile rather than long-lived access keys, and the Tailscale key was single-use and ephemeral, so the test machine left the tailnet after `terraform destroy`.

### Trade-offs
- File transfers between AWS and home are limited by my home internet upload speed.
- The NAS is only reachable while the laptop is awake and the VM is running.
- The pool is a single virtual disk with no redundancy fine for a lab, not a backup on its own.

---

## 🗺️ Roadmap

Planned expansions, checked off as they ship.

**Rebuild it right**
- [x] Rebuild the EC2 stack with **Terraform** + cloud-init (instance, security group, EBS) so it can be recreated with one command
- [x] Restrict the security group to Tailscale-only access and document the before/after

**Protect the data**
- [x] TrueNAS SCALE storage tier: ZFS pool, Tailscale, least-privilege SMB share (Phases 0–4)
- [x] Connect EC2 to the TrueNAS share over Tailscale (Phases 5–6)
- [ ] Nextcloud AIO **BorgBackup** to TrueNAS, with daily ZFS snapshots underneath
- [ ] Offsite copy to S3 Glacier for a full 3-2-1 backup strategy

**Extras**
- [ ] Nextcloud Assistant backed by a local LLM (Ollama) — AI features without files leaving my infrastructure

---

## 🚀 Deployment

### Prerequisites
- AWS account with EC2 access
- Tailscale account
- Ubuntu 24.04 LTS EC2 instance (t3.small minimum)
- Docker Engine installed

  

### ☁️ AWS Configurations
 
### Step 1 — AWS EC2 Setup
 
**EC2 Instance Configuration:**
 
| Setting | Value |
|---|---|
| Name | `your-instance` |
| AMI | Ubuntu Server 24.04 LTS (HVM) |
| AMI ID | Latest Ubuntu 24.04 LTS AMI for your region (AMI IDs are region-specific) |
| Instance Type | `t3.small` (2 vCPU, 2 GB RAM) |
| Region | us-east-2 (Ohio) |
| Storage | 30 GB gp3 |
| Key Pair | `your-instance.pem` |

 
**Security Group (Tailscale-only)**

CloudHUB is reached only over the tailnet, and Caddy uses Tailscale-issued certificates, so no web ports need to be open to the internet.

| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | My IP | SSH admin access during setup (remove once Tailscale SSH works) |
| 8080 | TCP | My IP | Nextcloud AIO setup interface (remove after initial setup) |
| 41641 | UDP | Anywhere | *Optional:* lets Tailscale make direct peer connections instead of relaying through DERP |

No rule for 80, 443, or 8443: all Nextcloud traffic arrives through the Tailscale tunnel. Outbound rules stay at the default (all traffic) so the instance can reach Tailscale, Docker Hub, and package mirrors.


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

### 🧱 Infrastructure as Code (Terraform)

The [`terraform/`](terraform/) folder recreates the EC2 side of CloudHUB from scratch: the latest Ubuntu 24.04 AMI, a security group with **no inbound rules** (all outbound), an encrypted 30 GB gp3 volume, IMDSv2-only metadata, and no SSH key pair — admin access is Tailscale SSH only. A cloud-init script then installs swap, Docker, Tailscale (with `--ssh`), Caddy with auto-renewing Tailscale certificates, and the Nextcloud AIO master container.

| File | Purpose |
|---|---|
| `versions.tf` | Terraform + AWS provider versions, default tags |
| `variables.tf` | Region, instance type, disk/swap size, Tailscale auth key (sensitive) |
| `main.tf` | AMI lookup, security group, EC2 instance |
| `cloud-init.yaml.tftpl` | Bootstrap script, logged to `/var/log/cloudhub-setup.log` |
| `outputs.tf` | Instance ID, IPs, next steps |
| `terraform.tfvars.example` | Copy to `terraform.tfvars` (git-ignored) and fill in |

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # add a one-off Tailscale auth key
terraform init
terraform plan
terraform apply
# ...test it...
terraform destroy
```

> The Tailscale auth key ends up in instance user data, so use a **single-use, ephemeral, short-expiry** key and never commit `terraform.tfvars`.

**Authenticate with SSO, not access keys:**

```bash
aws configure sso          # session name: cloudhub-sso, region: us-east-2, profile: cloudhub
aws sts get-caller-identity --profile cloudhub
aws sso login --profile cloudhub   # when the session expires
```

**Verified test run:** `plan` showed 2 to add (security group + instance). After `apply`, the security group had no inbound rules, the instance showed Connected (Ephemeral, SSH) in Tailscale, `cloud-init status` returned `done`, the setup log ended with `CloudHUB setup finished`, a 2 GB swapfile was active, and the AIO login page loaded on port 8080 over Tailscale. Then `destroy` removed both resources.

---

### 🏠 TrueNAS SCALE on Hyper-V (Hybrid Storage)

**Prerequisites**
- Windows 10/11 **Pro, Enterprise, or Education** (Hyper-V is not available on Home)
- 16 GB+ RAM on the host (the VM gets 16 GB fixed)
- ~120 GB free disk space
- TrueNAS SCALE / Community Edition ISO from [truenas.com](https://www.truenas.com/download-truenas-scale/), saved to your **Downloads** folder
- The CloudHUB EC2 host already on your Tailscale tailnet

**1. Keep the host awake**

A sleeping host pauses the VM and Nextcloud loses the share.
- **Settings → System → Power & battery → Screen, sleep & hibernate timeouts** → *Make my device sleep after* (plugged in): **Never**
- **Lid & power button controls** → *Closing the lid will make my PC* (plugged in): **Do Nothing**

**2. Check / enable Hyper-V** (PowerShell as Administrator):
```powershell
& {
  $os = (Get-CimInstance Win32_OperatingSystem).Caption
  Write-Host "Windows edition: $os"
  if ($os -match "Home") {
    Write-Host "Home edition: Hyper-V is not available. Stop here." -ForegroundColor Red
    return
  }
  $hv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
  if ($hv.State -eq "Enabled") {
    Write-Host "Hyper-V is already enabled. Skip the restart." -ForegroundColor Green
  } else {
    Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart | Out-Null
    Write-Host "Hyper-V enabled. Restart Windows, then continue." -ForegroundColor Yellow
  }
}
```

**3. Create the VM** (PowerShell as Administrator):

Pre-flight checks run first the script stops before creating anything if the ISO is missing, the VM name is taken, the switch doesn't exist, or there isn't enough free disk space.
```powershell
& {
  $VMName = "TrueNAS"
  $VMPath = "C:\HyperV\$VMName"
  $MemGB  = 16     # fixed RAM; ZFS uses it for caching
  $CPUs   = 4
  $BootGB = 32     # TrueNAS OS disk
  $DataGB = 64     # storage pool disk (dynamic: only grows as you fill it)

  $iso = Get-ChildItem "$env:USERPROFILE\Downloads" -Filter "TrueNAS*.iso" -ErrorAction SilentlyContinue |
         Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $iso) { Write-Host "No TrueNAS ISO found in Downloads. Download it, then rerun." -ForegroundColor Red; return }
  Write-Host "Using ISO: $($iso.Name)"

  if (Get-VM -Name $VMName -ErrorAction SilentlyContinue) {
    Write-Host "A VM named '$VMName' already exists. Stopping so nothing gets overwritten." -ForegroundColor Yellow; return
  }
  if (-not (Get-VMSwitch -Name "Default Switch" -ErrorAction SilentlyContinue)) {
    Write-Host "Hyper-V 'Default Switch' not found. Did you restart after enabling Hyper-V?" -ForegroundColor Red; return
  }
  $freeGB = [math]::Round((Get-PSDrive C).Free / 1GB)
  if ($freeGB -lt ($BootGB + $DataGB + 20)) {
    Write-Host "Only $freeGB GB free on C:. Lower `$DataGB and rerun." -ForegroundColor Red; return
  }

  New-Item -ItemType Directory -Path $VMPath -Force | Out-Null
  New-VM -Name $VMName -Generation 2 -MemoryStartupBytes ($MemGB * 1GB) -Path $VMPath `
         -NewVHDPath "$VMPath\boot.vhdx" -NewVHDSizeBytes ($BootGB * 1GB) -SwitchName "Default Switch" | Out-Null
  Set-VMMemory    -VMName $VMName -DynamicMemoryEnabled $false   # TrueNAS needs fixed memory
  Set-VMProcessor -VMName $VMName -Count $CPUs
  Set-VM          -Name   $VMName -CheckpointType Disabled       # use ZFS snapshots instead
  New-VHD -Path "$VMPath\data.vhdx" -SizeBytes ($DataGB * 1GB) -Dynamic | Out-Null
  Add-VMHardDiskDrive -VMName $VMName -Path "$VMPath\data.vhdx"
  $dvd = Add-VMDvdDrive -VMName $VMName -Path $iso.FullName -Passthru
  Set-VMFirmware -VMName $VMName -EnableSecureBoot Off -FirstBootDevice $dvd

  Write-Host "VM '$VMName' created: $MemGB GB RAM, $CPUs CPUs, $BootGB GB boot disk, $DataGB GB data disk." -ForegroundColor Green
}
```

**4. Install TrueNAS**
1. **Hyper-V Manager** → right-click **TrueNAS** → **Connect** → **Start**
2. Press any key at *"Press any key to boot from CD or DVD"* (it only shows for a few seconds)
3. **Install/Upgrade** → select the **32 GB** disk only → set the `truenas_admin` password
4. **Media → DVD Drive → Eject**, then reboot
5. Open the web UI address shown on the console (e.g. `http://172.x.x.x`) in a browser on the host

**5. Create the pool** — **Storage → Create Pool**
- Name: `tank` · Layout: **Stripe** · Disk: the **64 GB** data disk
- If prompted, allow non-unique disk serials (normal for Hyper-V virtual disks)

**6. Join the tailnet** — **Apps → Discover Apps → Tailscale** (community train; choose `tank` as the apps pool)

| Setting | Value |
|---|---|
| Auth Key | single-use key from Tailscale admin → Settings → Keys |
| Hostname | your choice |
| Userspace | ☐ **unchecked** |
| Host Network | ☑ **enabled** |

Host networking with userspace off is what lets Nextcloud reach the SMB service on the TrueNAS host itself. In the Tailscale admin console, **Disable key expiry** on the NAS so it doesn't drop off later.

**7. Dataset, user, and share**
1. **Datasets** → `tank` → **Add Dataset** → name `cloudhub`, preset **SMB**
2. **Credentials → Users → Add** → `nextcloud-smb`, **SMB access only** (no shell, no TrueNAS access)
3. **Datasets** → `cloudhub` → **Permissions → Edit** → add **User `nextcloud-smb` · Modify**
4. **Shares → SMB** → confirm share `cloudhub` → `/mnt/tank/cloudhub` is enabled
5. **System → Services** → **SMB**: Running, **Start Automatically** on

**8. Verify from EC2** (SSH into the CloudHUB instance):
```bash
NAS_IP="100.x.y.z"   # <-- your TrueNAS Tailscale IP

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale is not installed on this host — stop here."
else
  echo "== Tailscale ping to TrueNAS =="
  sudo tailscale ping -c 3 "$NAS_IP" || echo "Ping failed — check both machines show Connected."

  echo "== SMB port 445 =="
  if command -v nc >/dev/null 2>&1; then
    nc -zvw5 "$NAS_IP" 445 && echo "Port 445 reachable" || echo "Port 445 blocked — check Tailscale ACLs."
  else
    timeout 5 bash -c "echo > /dev/tcp/$NAS_IP/445" && echo "Port 445 reachable" || echo "Port 445 blocked — check Tailscale ACLs."
  fi
fi
```

**9. Mount in Nextcloud** — **Apps** → enable **External storage support**, then **Administration settings → External storage**:

| Field | Value |
|---|---|
| Folder name | `TrueNAS` |
| External storage | SMB/CIFS |
| Authentication | Username and password |
| Host | your TrueNAS Tailscale IP (use the IP, not the MagicDNS name) |
| Share | `cloudhub` |
| Username / Password | `nextcloud-smb` credentials |

A green dot next to the mount means it's connected.

**10. Protect it** — **Data Protection → Periodic Snapshot Tasks → Add** → dataset `tank/cloudhub`, daily, ~2 weeks retention. Make sure your home router does **not** forward port 445.

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
| Public IPv4 address | ~$3.60 (AWS charges for all public IPv4 since Feb 2024) |
| Data Transfer | ~$1–3.00 |
| Tailscale | $0.00 (free plan) |
| TrueNAS home tier | $0.00 (existing hardware, free Community Edition) |
| **Total** | **~$22–24/mo** |

---
