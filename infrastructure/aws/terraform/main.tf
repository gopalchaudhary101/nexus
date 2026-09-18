# NEXUS — AWS production infrastructure (primary cloud).
#
# Provisions: VPC (2 public / 2 private subnets), ECS Fargate service for the
# API, RDS PostgreSQL 16 (pgvector), S3 uploads bucket, SQS job queue,
# Secrets Manager secret, ALB with HTTP listener, IAM roles (least privilege),
# CloudWatch log group + 5xx alarm.
#
# Usage:
#   terraform init -backend-config="bucket=<state-bucket>" -backend-config="key=nexus/prod.tfstate"
#   terraform apply
#
# The ECS task definition is created via data/locals below; replace the
# image ARN (var.api_image) with your pushed image (ECR or public).

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" { default = "ap-south-1" }
variable "env"        { default = "prod" }
variable "api_image"  { description = "Container image for the API task" }
variable "vpc_cidr"   { default = "10.40.0.0/16" }

locals {
  name       = "nexus-${var.env}"
  common_tags = { Project = "nexus", Environment = var.env, ManagedBy = "terraform" }
}

# ── VPC ──────────────────────────────────────────────────────────────────
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = local.name
  cidr = var.vpc_cidr

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.40.1.0/24", "10.40.2.0/24"]
  public_subnets  = ["10.40.101.0/24", "10.40.102.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  public_subnet_tags = { "kubernetes.io/role/elb" = 1 }
}

# ── Security groups ──────────────────────────────────────────────────────
resource "aws_security_group" "api" {
  name_prefix = "${local.name}-api-"
  vpc_id      = module.vpc.vpc_id
  tags        = local.common_tags

  ingress {
    description = "from ALB only"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "alb" {
  name_prefix = "${local.name}-alb-"
  vpc_id      = module.vpc.vpc_id
  tags        = local.common_tags

  ingress {
    description = "HTTP (TLS terminated at ALB; route 443 listener via cert manager/ACM in real deployments)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── RDS PostgreSQL (pgvector-capable) ────────────────────────────────────
resource "aws_db_subnet_group" "nexus" {
  name       = local.name
  subnet_ids = module.vpc.private_subnet_ids
  tags       = local.common_tags
}

resource "aws_db_instance" "nexus" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = "db.t4g.micro"
  allocated_storage     = 20
  max_allocated_storage = 80
  storage_encrypted     = true
  multi_az              = true
  db_name               = "nexus"
  username              = "nexus"
  manage_master_user_password = true
  db_subnet_group_name   = aws_db_subnet_group.nexus.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  tags                   = local.common_tags
}

resource "aws_security_group" "rds" {
  name_prefix = "${local.name}-rds-"
  vpc_id      = module.vpc.vpc_id
  tags        = local.common_tags

  ingress {
    description = "postgres from api SG"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    security_groups = [aws_security_group.api.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── S3 uploads (private, versioned, encrypted) ───────────────────────────
resource "aws_s3_bucket" "uploads" {
  bucket = "${local.name}-uploads-${var.aws_region}"
  tags   = local.common_tags
}
resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
  }
}

# ── SQS (production job queue behind JobRunner.submit) ──────────────────
resource "aws_sqs_queue" "jobs" {
  name                      = "${local.name}-jobs"
  visibility_timeout_seconds = 600
  message_retention_seconds  = 345600
  tags                       = local.common_tags
}

# ── Secrets Manager ──────────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "api" {
  name   = "${local.name}/api"
  tags   = local.common_tags
}
# Put NEXUS_SECRET_KEY, DB password, provider keys in this secret (ops step)
# and render them into the task definition env at deploy time.
resource "aws_secretsmanager_secret_version" "api" {
  secret_id = aws_secretsmanager_secret.api.id
  secret_string = jsonencode({
    NEXUS_SECRET_KEY = random_string.jwt.result
  })
}
resource "random_string" "jwt" {
  length  = 48
  special = false
}

# ── ECS cluster + service (Fargate) ──────────────────────────────────────
resource "aws_ecs_cluster" "nexus" {
  name = local.name
  settings {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name  = "nexus-api"
    image = var.api_image
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment = [
      { name = "NEXUS_HOST", value = "0.0.0.0" },
      { name = "NEXUS_PORT", value = "8000" },
      { name = "NEXUS_USE_PGVECTOR", value = "1" },
      {
        name      = "NEXUS_DATABASE_URL"
        valueFrom = "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${aws_secretsmanager_secret.api.name}"
      },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"  = aws_cloudwatch_log_group.api.name
        "awslogs-region" = var.aws_region
        "awslogs-stream-prefix" = "nexus-api"
      }
    }
  }])
  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = 30
  tags              = local.common_tags
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.nexus.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"
  propagation_seconds = 30

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "nexus-api"
    container_port   = 8000
  }

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.api.id]
  }

  depends_on = [aws_db_instance.nexus]
}

# ── ALB ──────────────────────────────────────────────────────────────────
data "aws_caller_identity" "current" {}

resource "aws_lb" "api" {
  name               = local.name
  load_balancer_type = "application"
  subnets            = module.vpc.public_subnets
  security_groups    = [aws_security_group.alb.id]
  tags               = local.common_tags
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {
    path                = "/api/v1/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
  }

  tags = local.common_tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# ── IAM (least privilege) ────────────────────────────────────────────────
data "aws_iam_policy_document" "ecs_exec" {
  statement {
    effect  = "Allow"
    actions = ["ecs:ExecuteCommand"]
    resources = ["*"]
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-ecs-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_exec.assume.json
}
data "aws_iam_policy_document" "ecs_task_exec" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}
resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "execution" {
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.ecs_exec.json
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_exec.assume.json
}
data "aws_iam_policy_document" "task" {
  statement {
    sid     = "S3Uploads"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [
      aws_s3_bucket.uploads.arn,
      "${aws_s3_bucket.uploads.arn}/*",
    ]
  }
  statement {
    sid     = "SQSJobs"
    effect  = "Allow"
    actions = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueUrl"]
    resources = [aws_sqs_queue.jobs.arn]
  }
  statement {
    sid     = "SecretsRead"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api.arn]
  }
  statement {
    sid     = "RDSProxy"
    effect  = "Allow"
    actions = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:${var.aws_region}:${data.aws_caller_identity.current.account_id}:dbuser:${aws_db_instance.nexus.id}/nexus"]
  }
}
resource "aws_iam_role_policy" "task" {
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# ── Observability ────────────────────────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_actions       = []
  dimensions = {
    LoadBalancer = aws_lb.api.arn_suffix
  }
  tags = local.common_tags
}

output "alb_dns" {
  value = aws_lb.api.dns_name
}
output "rds_endpoint" {
  value = aws_db_instance.nexus.endpoint
}
output "uploads_bucket" {
  value = aws_s3_bucket.uploads.bucket
}
