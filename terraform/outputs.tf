output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.cloudhub.id
}

output "public_ip" {
  description = "Public IPv4 (used only for outbound traffic; no inbound ports are open)."
  value       = aws_instance.cloudhub.public_ip
}

output "security_group_id" {
  description = "Security group ID."
  value       = aws_security_group.cloudhub.id
}

output "ami_id" {
  description = "Ubuntu AMI used."
  value       = data.aws_ami.ubuntu.id
}

output "next_steps" {
  description = "What to do after apply."
  value       = <<-EOT
    1. Wait ~5 minutes for cloud-init to finish.
    2. Confirm '${var.name}' shows Connected at https://login.tailscale.com/admin/machines
    3. ssh ubuntu@${var.name}   (Tailscale SSH; use its 100.x IP if the name doesn't resolve)
    4. On the instance: cat /var/log/cloudhub-setup.log  and  cat /root/cloudhub-url.txt
    5. Open the AIO setup at https://<tailscale-ip>:8080
  EOT
}
