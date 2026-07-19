terraform {
  required_version = ">= 1.5"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.5" }
  }
}

provider "aws" {
  region = var.aws_region
}

# ponytail: default VPC + its subnets instead of a hand-rolled network module.
# Fine for a single-box team deploy; swap in a dedicated VPC if policy requires.
data "aws_vpc" "default" { default = true }

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

data "aws_kms_alias" "ssm" { name = "alias/aws/ssm" }

# --- Secrets: generate the DB password, stash everything as SecureString ------
resource "random_password" "db" {
  length  = 24
  special = false # ponytail: alnum only, so the password drops cleanly into the DSN with no %-encoding
}

resource "aws_ssm_parameter" "database_url" {
  name  = "${var.ssm_prefix}/database_url"
  type  = "SecureString"
  value = "postgresql+psycopg2://approvo:${random_password.db.result}@${aws_db_instance.this.address}:5432/approvo"
}

resource "aws_ssm_parameter" "gh_client_id" {
  name  = "${var.ssm_prefix}/oauth_github_client_id"
  type  = "SecureString"
  value = var.github_client_id
}

resource "aws_ssm_parameter" "gh_client_secret" {
  name  = "${var.ssm_prefix}/oauth_github_client_secret"
  type  = "SecureString"
  value = var.github_client_secret
}

# --- Networking: two SGs, RDS only reachable from the app box -----------------
resource "aws_security_group" "ec2" {
  name        = "approvo-ec2"
  description = "Approvo app box: HTTP/HTTPS in, optional SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP (users + Let's Encrypt challenge)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  dynamic "ingress" {
    for_each = var.ssh_key_name != "" && var.admin_cidr != "" ? [1] : []
    content {
      description = "SSH (admin only)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [var.admin_cidr]
    }
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds" {
  name        = "approvo-rds"
  description = "Postgres reachable only from the app box"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from the app box"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Managed Postgres ---------------------------------------------------------
resource "aws_db_subnet_group" "this" {
  name       = "approvo"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "this" {
  identifier             = "approvo"
  engine                 = "postgres"
  instance_class         = "db.t4g.micro"
  allocated_storage      = 20
  storage_encrypted      = true
  db_name                = "approvo"
  username               = "approvo"
  password               = random_password.db.result
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  backup_retention_period = 7 # daily backups kept — data-loss protection stays ON
  skip_final_snapshot     = true
  # ponytail: single-AZ, destroyable. For production flip: multi_az=true,
  # deletion_protection=true, skip_final_snapshot=false + final_snapshot_identifier.
}

# --- IAM: instance role reads the SSM secrets + Session Manager shell ----------
resource "aws_iam_role" "ec2" {
  name = "approvo-ec2"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "secrets" {
  name = "approvo-read-secrets"
  role = aws_iam_role.ec2.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter${var.ssm_prefix}/*"
      },
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = data.aws_kms_alias.ssm.target_key_arn
      }
    ]
  })
}

# Session Manager: shell into the box with no open SSH port.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "approvo-ec2"
  role = aws_iam_role.ec2.name
}

# --- The app box --------------------------------------------------------------
resource "aws_instance" "app" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  key_name               = var.ssh_key_name != "" ? var.ssh_key_name : null

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    domain      = var.domain
    region      = var.aws_region
    ssm_prefix  = var.ssm_prefix
    repo_url    = var.repo_url
    repo_branch = var.repo_branch
  })

  metadata_options {
    http_tokens   = "required" # IMDSv2 only
    http_endpoint = "enabled"
  }

  root_block_device {
    volume_size = 20
    encrypted   = true
  }

  # Boot only after the DB is available AND the secrets exist — cloud-init reads
  # both at startup. (database_url param already depends on the RDS endpoint.)
  depends_on = [
    aws_ssm_parameter.database_url,
    aws_ssm_parameter.gh_client_id,
    aws_ssm_parameter.gh_client_secret,
  ]

  tags = { Name = "approvo-app" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
}

# --- Optional DNS -------------------------------------------------------------
resource "aws_route53_record" "app" {
  count   = var.route53_zone_id != "" ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}
