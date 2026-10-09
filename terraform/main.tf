# --- Ubuntu 24.04 LTS (latest, from Canonical) ------------------------------
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# --- Default VPC -----------------------------------------------------------
data "aws_vpc" "default" {
  default = true
}

# --- Security group: no inbound by default, all outbound --------------------
# All access to CloudHUB (web UI, AIO admin, SSH) goes through Tailscale,
# which only needs outbound connectivity.
resource "aws_security_group" "cloudhub" {
  name        = "${var.name}-tailscale-only"
  description = "CloudHUB: no public inbound; access via Tailscale only"
  vpc_id      = data.aws_vpc.default.id

  tags = {
    Name = "${var.name}-tailscale-only"
  }
}

resource "aws_vpc_security_group_egress_rule" "all_out" {
  security_group_id = aws_security_group.cloudhub.id
  description       = "All outbound (Tailscale, Docker Hub, package mirrors)"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "tailscale_direct" {
  count             = var.allow_tailscale_direct_udp ? 1 : 0
  security_group_id = aws_security_group.cloudhub.id
  description       = "Tailscale direct connections (optional)"
  ip_protocol       = "udp"
  from_port         = 41641
  to_port           = 41641
  cidr_ipv4         = "0.0.0.0/0"
}

# --- EC2 instance ------------------------------------------------------------
resource "aws_instance" "cloudhub" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  vpc_security_group_ids      = [aws_security_group.cloudhub.id]
  associate_public_ip_address = true # outbound internet without a NAT gateway

  # No key pair: admin access is Tailscale SSH only.

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    hostname           = var.name
    tailscale_auth_key = var.tailscale_auth_key
    swap_gb            = var.swap_gb
  })
  user_data_replace_on_change = true

  tags = {
    Name = var.name
  }
}
