# 应用负载均衡器配置（可选）

# ALB（如果使用）
resource "aws_lb" "main" {
  count = var.use_existing_vpc ? 0 : 1

  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-alb"
  })
}

# API目标组
resource "aws_lb_target_group" "api" {
  count = var.use_existing_vpc ? 0 : 1

  name     = "${var.project_name}-${var.environment}-api-tg"
  port     = 5005
  protocol = "HTTP"
  vpc_id   = aws_vpc.main[0].id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/health"
    matcher             = "200"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-api-tg"
  })
}

# Web目标组
resource "aws_lb_target_group" "web" {
  count = var.use_existing_vpc ? 0 : 1

  name     = "${var.project_name}-${var.environment}-web-tg"
  port     = 3000
  protocol = "HTTP"
  vpc_id   = aws_vpc.main[0].id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200"
    port                = "traffic-port"
    protocol            = "HTTP"
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-web-tg"
  })
}

# 目标组注册
resource "aws_lb_target_group_attachment" "api" {
  count = var.use_existing_vpc ? 0 : 1

  target_group_arn = aws_lb_target_group.api[0].arn
  target_id        = local.instance_id
  port             = 5005
}

resource "aws_lb_target_group_attachment" "web" {
  count = var.use_existing_vpc ? 0 : 1

  target_group_arn = aws_lb_target_group.web[0].arn
  target_id        = local.instance_id
  port             = 3000
}

# HTTP监听器
resource "aws_lb_listener" "http" {
  count = var.use_existing_vpc ? 0 : 1

  load_balancer_arn = aws_lb.main[0].arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS监听器
resource "aws_lb_listener" "https" {
  count = var.use_existing_vpc ? 0 : 1

  load_balancer_arn = aws_lb.main[0].arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = var.ssl_certificate_arn != "" ? var.ssl_certificate_arn : aws_acm_certificate.main[0].arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web[0].arn
  }
}

# API路径规则
resource "aws_lb_listener_rule" "api" {
  count = var.use_existing_vpc ? 0 : 1

  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api[0].arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

# ACM证书（如果启用SSL且未提供证书）
resource "aws_acm_certificate" "main" {
  count = var.enable_ssl && var.ssl_certificate_arn == "" ? 1 : 0

  domain_name = var.domain_name
  subject_alternative_names = [
    "${var.api_subdomain}.${var.domain_name}",
    "${var.web_subdomain}.${var.domain_name}"
  ]
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-certificate"
  })
}

# 证书验证
resource "aws_acm_certificate_validation" "main" {
  count = 0  # 暂时禁用，需要手动验证DNS

  certificate_arn         = aws_acm_certificate.main[0].arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]

  timeouts {
    create = "5m"
  }
}

# Route53记录（如果使用Route53）
resource "aws_route53_zone" "main" {
  count = 0  # 暂时禁用Route53，因为使用现有VPC

  name = var.domain_name

  tags = merge(var.common_tags, {
    Name = "${var.project_name}-${var.environment}-zone"
  })
}

# API DNS记录
resource "aws_route53_record" "api" {
  count = 0  # 暂时禁用Route53

  zone_id = aws_route53_zone.main[0].zone_id
  name    = "${var.api_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main[0].dns_name
    zone_id                = aws_lb.main[0].zone_id
    evaluate_target_health = true
  }
}

# Web DNS记录
resource "aws_route53_record" "web" {
  count = 0  # 暂时禁用Route53

  zone_id = aws_route53_zone.main[0].zone_id
  name    = "${var.web_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main[0].dns_name
    zone_id                = aws_lb.main[0].zone_id
    evaluate_target_health = true
  }
}

# 证书验证记录
resource "aws_route53_record" "cert_validation" {
  for_each = {}  # 暂时禁用Route53

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main[0].zone_id
}
