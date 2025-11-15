# 应用负载均衡器 - 多环境支持
resource "aws_lb" "main" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = var.environment == "prod"

  tags = {
    Name        = "${var.project_name}-${var.environment}-alb"
    Environment = var.environment
    Project     = var.project_name
  }
}

# 目标组 - 后端
resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-${var.environment}-backend-tg"
  port        = 5005
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-backend-tg"
    Environment = var.environment
  }
}

# 目标组 - 前端
resource "aws_lb_target_group" "frontend" {
  name        = "${var.project_name}-${var.environment}-frontend-tg"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-frontend-tg"
    Environment = var.environment
  }
}

# 监听器 - HTTP
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
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

# 监听器 - HTTPS
# 注意：AWS不允许使用未验证的证书创建HTTPS监听器
# 如果use_route53=false，需要先手动完成证书验证，然后重新应用此配置
# 暂时不创建HTTPS监听器，等证书验证完成后再创建
resource "aws_lb_listener" "https" {
  count = var.use_route53 ? 1 : 0  # 只有在使用Route53自动验证时才创建
  
  load_balancer_arn = aws_lb.main.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = aws_acm_certificate_validation.main[0].certificate_arn

  # 默认路由到前端（如果没有匹配的规则）
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# 监听器规则 - API路由（基于Host header）
resource "aws_lb_listener_rule" "api" {
  count = var.use_route53 ? 1 : 0  # 只有在HTTPS监听器存在时才创建
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    host_header {
      values = var.environment == "prod" ? ["api.${var.domain_name}"] : (var.environment == "dev" ? ["apidev.${var.domain_name}"] : (var.environment == "test" ? ["apitest.${var.domain_name}"] : ["${var.environment}-api.${var.domain_name}"]))
    }
  }
}

# 监听器规则 - Web路由（基于Host header，确保dev.knowhereto.ai路由到前端）
resource "aws_lb_listener_rule" "web" {
  count = var.use_route53 ? 1 : 0  # 只有在HTTPS监听器存在时才创建
  
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  condition {
    host_header {
      values = var.environment == "prod" ? [var.domain_name, "www.${var.domain_name}"] : ["${var.environment}.${var.domain_name}"]
    }
  }
}

# SSL证书 - 多环境域名支持
resource "aws_acm_certificate" "main" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  subject_alternative_names = concat(
    var.environment == "dev" ? ["apidev.${var.domain_name}", "dev.${var.domain_name}"] : [],
    var.environment == "test" ? ["apitest.${var.domain_name}", "test.${var.domain_name}"] : [],
    var.environment == "prod" ? ["api.${var.domain_name}", "www.${var.domain_name}"] : []
  )

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-certificate"
    Environment = var.environment
  }
}

# 证书验证
# 如果使用Route53，等待自动验证；否则需要手动在外部DNS创建验证记录
resource "aws_acm_certificate_validation" "main" {
  count = var.use_route53 ? 1 : 0
  
  certificate_arn         = aws_acm_certificate.main.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# 使用现有的Route53托管区域（仅在use_route53=true时使用）
data "aws_route53_zone" "main" {
  count = var.use_route53 ? 1 : 0
  name  = var.domain_name
}

# Route53记录 - 多环境域名（仅在use_route53=true时创建）
resource "aws_route53_record" "main" {
  count = var.use_route53 && var.environment == "prod" ? 1 : 0

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "api" {
  count = var.use_route53 ? 1 : 0

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.environment == "prod" ? "api.${var.domain_name}" : (var.environment == "dev" ? "apidev.${var.domain_name}" : (var.environment == "test" ? "apitest.${var.domain_name}" : "${var.environment}-api.${var.domain_name}"))
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "web" {
  count = var.use_route53 ? 1 : 0

  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = var.environment == "prod" ? var.domain_name : "${var.environment}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# 证书验证记录（仅在use_route53=true时自动创建）
resource "aws_route53_record" "cert_validation" {
  for_each = var.use_route53 ? {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main[0].zone_id
}

# 变量定义在 variables.tf 中
