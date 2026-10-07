# ☁️ CloudHUB — Hybrid Self-Hosted Cloud


<img width="400" height="351" alt="CloudHUB-removebg-preview" src="https://github.com/user-attachments/assets/5ecebe41-9061-41e6-bfcb-8501ae880667" />





---

> My personal productivity workspace a self-hosted Nextcloud instance running on AWS EC2, secured with Tailscale VPN and deployed via Docker. Expanded into a hybrid setup, with bulk storage on a home TrueNAS SCALE server reached over the same tailnet.

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

It runs on AWS EC2, is accessible only through Tailscale VPN, and serves as my central hub for all productivity work from writing and file management to video calls and collaborative documents.

--- 

### What's new?

### 🧱 Hybrid Storage
30 GB of cloud storage fills up fast. Rather than pay for a larger EBS volume, I set up a TrueNAS SCALE server at home and mounted its share in Nextcloud over Tailscale. Users still access everything through CloudHUB on EC2, with no ports exposed on my home network.

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

---

## 🛠️ Tech Stack

### Infrastructure
| Component | Technology |
|---|---|
| Cloud Provider | AWS EC2 (t3.small, us-east-1) |
| OS | Ubuntu Server 24.04 LTS |
| Storage | 30 GB gp3 EBS Volume |
| Static IP | AWS Elastic IP |

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
- **AWS Security Groups** — SSH restricted to admin IP; ports locked down
- **AIO Reverse Proxy Mode** — Caddy handles TLS termination, Nextcloud never directly exposed
- **Private Magic DNS** — domain only resolvable inside the Tailscale network
- **NAS reachable only over the tailnet** — the TrueNAS SMB share is reached at its Tailscale address; no ports are forwarded on the home router
- **Least-privilege SMB account** — Nextcloud connects as a dedicated `nextcloud-smb` user with SMB access only (no shell, no TrueNAS admin access, no API keys) and Modify rights on the one dataset it needs

---

## 🧱 Hybrid Storage: TrueNAS SCALE

The goal: keep Nextcloud on EC2 as the single entry point, and move bulk files to ZFS storage at home.

### Why a VM on a laptop?
My main machine didn't have the free space, so I repurposed a Surface Book 3. It has no Ethernet port (and TrueNAS doesn't support Wi-Fi) and only one internal drive, so instead of installing TrueNAS on the bare metal I run it as a **Hyper-V VM**. The VM uses Hyper-V's Default Switch for outbound internet; once Tailscale runs inside TrueNAS, everything else reaches it at its tailnet address.

### Progress
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
| 7 | Harden: daily ZFS snapshots, tighten the dataset ACL, verify no port forwarding | ✅ Done |

### Lessons learned
- **The pre-flight checks paid off.** The VM script refused to run on the first attempt because the host only had 131 GB free not enough for the planned 256 GB data disk plus margin. Dropping the data disk to 64 GB (dynamic, so it only grows as it fills) fixed it before anything was created.
- **Tailscale needs host networking for this use case.** The TrueNAS Tailscale app's default (userspace) mode suits reaching the web UI, but Nextcloud needs to reach the SMB service on the TrueNAS host itself so the app runs with host network enabled and userspace disabled.
- **If the NAS drops off the tailnet, restart the app first.** The app showed Running while the machine showed offline in the Tailscale console; a restart reconnected it.

### Trade-offs
- File transfers between AWS and home are limited by my home internet upload speed.
- The NAS is only reachable while the laptop is awake and the VM is running.
- The pool is a single virtual disk with no redundancy fine for a lab, not a backup on its own.

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
| AMI ID | `ami-05cf1e9f73fbad2e2` |
| Instance Type | `t3.small` (2 vCPU, 2 GB RAM) |
| Region | us-east-1 (N. Virginia) |
| Storage | 30 GB gp3 |
| Key Pair | `your-instance.pem` |

 
**Security Group**
 
| Port | Protocol | Source | Purpose |
|---|---|---|---|
| 22 | TCP | My IP | SSH admin access |
| 443 | TCP | Anywhere | HTTPS web traffic |
| 8080 | TCP | My IP | Nextcloud AIO dashboard |
| 8443 | TCP | My IP | Nextcloud AIO dashboard HTTPS |


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

Pre-flight checks run first — the script stops before creating anything if the ISO is missing, the VM name is taken, the switch doesn't exist, or there isn't enough free disk space.
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
  echo "Tailscale is not installed on this host stop here."
else
  echo "== Tailscale ping to TrueNAS =="
  sudo tailscale ping -c 3 "$NAS_IP" || echo "Ping failed check both machines show Connected."

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
| Elastic IP | $0.00 (attached) |
| Data Transfer | ~$1–3.00 |
| Tailscale | $0.00 (free plan) |
| TrueNAS home tier | $0.00 (existing hardware, free Community Edition) |
| **Total** | **~$18–20/mo** |

---
