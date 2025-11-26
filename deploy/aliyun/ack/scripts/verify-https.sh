#!/bin/bash

# HTTPS 配置验证脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[✓] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[!] $1${NC}"
}

error() {
    echo -e "${RED}[✗] $1${NC}"
}

info() {
    echo -e "${BLUE}[i] $1${NC}"
}

NAMESPACE=${NAMESPACE:-knowhere}
SECRET_NAME=${SECRET_NAME:-knowhere-tls}

echo "=========================================="
echo "HTTPS 配置验证"
echo "=========================================="
echo ""

# 1. 检查 TLS Secret
echo "1. 检查 TLS Secret..."
if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
    log "TLS Secret '$SECRET_NAME' 已存在"
    
    # 检查Secret类型
    SECRET_TYPE=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.type}' 2>/dev/null || echo "")
    if [ "$SECRET_TYPE" = "kubernetes.io/tls" ]; then
        log "Secret类型正确: $SECRET_TYPE"
    else
        warn "Secret类型可能不正确: $SECRET_TYPE (期望: kubernetes.io/tls)"
    fi
    
    # 检查证书和私钥是否存在
    CERT_KEY=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.tls\.crt}' 2>/dev/null || echo "")
    KEY_KEY=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.tls\.key}' 2>/dev/null || echo "")
    
    if [ -n "$CERT_KEY" ] && [ -n "$KEY_KEY" ]; then
        log "证书和私钥数据已存在"
    else
        error "证书或私钥数据缺失"
        exit 1
    fi
else
    error "TLS Secret '$SECRET_NAME' 不存在"
    info "创建命令: ./create-tls-secret.sh"
    exit 1
fi

# 2. 检查证书信息
echo ""
echo "2. 检查证书信息..."
if command -v openssl &> /dev/null; then
    CERT_DATA=$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.tls\.crt}' 2>/dev/null || echo "")
    if [ -n "$CERT_DATA" ]; then
        CERT_INFO=$(echo "$CERT_DATA" | base64 -d 2>/dev/null | openssl x509 -noout -text 2>/dev/null || echo "")
        if [ -n "$CERT_INFO" ]; then
            # 提取证书主题
            SUBJECT=$(echo "$CERT_INFO" | grep "Subject:" | sed 's/Subject: //' || echo "")
            if [ -n "$SUBJECT" ]; then
                info "证书主题: $SUBJECT"
            fi
            
            # 提取SAN（Subject Alternative Names）
            SAN=$(echo "$CERT_INFO" | grep -A 1 "Subject Alternative Name" | tail -1 | sed 's/.*DNS://g' | sed 's/, /, /g' || echo "")
            if [ -n "$SAN" ]; then
                info "证书域名: $SAN"
            fi
            
            # 提取有效期
            NOT_BEFORE=$(echo "$CERT_INFO" | grep "Not Before" | sed 's/.*Not Before: //' || echo "")
            NOT_AFTER=$(echo "$CERT_INFO" | grep "Not After" | sed 's/.*Not After : //' || echo "")
            if [ -n "$NOT_BEFORE" ] && [ -n "$NOT_AFTER" ]; then
                info "有效期: $NOT_BEFORE 至 $NOT_AFTER"
                
                # 检查证书是否过期
                EXPIRY_EPOCH=$(echo "$CERT_DATA" | base64 -d 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 | xargs -I {} date -d {} +%s 2>/dev/null || echo "")
                CURRENT_EPOCH=$(date +%s)
                if [ -n "$EXPIRY_EPOCH" ] && [ "$EXPIRY_EPOCH" -gt "$CURRENT_EPOCH" ]; then
                    DAYS_LEFT=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))
                    if [ "$DAYS_LEFT" -lt 30 ]; then
                        warn "证书将在 $DAYS_LEFT 天后过期，请及时更新"
                    else
                        log "证书有效期正常（剩余 $DAYS_LEFT 天）"
                    fi
                fi
            fi
        fi
    fi
else
    warn "openssl 未安装，无法检查证书详细信息"
fi

# 3. 检查 Ingress 配置
echo ""
echo "3. 检查 Ingress 配置..."
INGRESS_COUNT=$(kubectl get ingress -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$INGRESS_COUNT" -ge 1 ]; then
    log "Ingress已配置 ($INGRESS_COUNT个)"
    
    # 检查TLS配置
    INGRESS_TLS=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].spec.tls[*].secretName}' 2>/dev/null || echo "")
    if echo "$INGRESS_TLS" | grep -q "$SECRET_NAME"; then
        log "Ingress已配置TLS，引用Secret: $SECRET_NAME"
        
        # 获取TLS hosts
        TLS_HOSTS=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].spec.tls[*].hosts[*]}' 2>/dev/null || echo "")
        if [ -n "$TLS_HOSTS" ]; then
            info "TLS域名: $TLS_HOSTS"
        fi
    else
        warn "Ingress未引用TLS Secret '$SECRET_NAME'"
    fi
    
    # 检查SSL重定向
    SSL_REDIRECT=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.annotations.nginx\.ingress\.kubernetes\.io/ssl-redirect}' 2>/dev/null || echo "")
    if echo "$SSL_REDIRECT" | grep -q "true"; then
        log "SSL重定向已启用"
    else
        warn "SSL重定向未启用"
    fi
else
    warn "Ingress未配置"
fi

# 4. 检查 Ingress Controller
echo ""
echo "4. 检查 Ingress Controller..."
if kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller &>/dev/null; then
    log "Ingress Controller (nginx) 已安装"
    
    # 获取LoadBalancer IP
    INGRESS_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [ -n "$INGRESS_IP" ]; then
        info "LoadBalancer IP: $INGRESS_IP"
    else
        warn "LoadBalancer IP未分配"
    fi
    
    # 检查Ingress Controller Pod状态
    INGRESS_PODS=$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller --no-headers 2>/dev/null | wc -l | tr -d ' ')
    RUNNING_PODS=$(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
    if [ "$RUNNING_PODS" -eq "$INGRESS_PODS" ] && [ "$INGRESS_PODS" -gt 0 ]; then
        log "Ingress Controller Pod运行正常 ($RUNNING_PODS/$INGRESS_PODS)"
    else
        warn "Ingress Controller Pod状态异常 ($RUNNING_PODS/$INGRESS_PODS)"
    fi
else
    error "Ingress Controller未安装或未运行"
    info "安装命令: ./install-ingress-controller.sh"
fi

# 5. 测试 HTTPS 访问
echo ""
echo "5. 测试 HTTPS 访问..."
INGRESS_HOSTS=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].spec.rules[*].host}' 2>/dev/null || echo "")
if [ -n "$INGRESS_HOSTS" ]; then
    if command -v curl &> /dev/null; then
        for host in $INGRESS_HOSTS; do
            info "测试 https://$host"
            
            # 测试HTTPS连接
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -k "https://$host" 2>/dev/null || echo "000")
            
            if [ "$HTTP_CODE" = "200" ]; then
                log "  ✓ HTTPS访问正常 (HTTP 200)"
            elif [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
                log "  ✓ HTTPS重定向正常 (HTTP $HTTP_CODE)"
            elif [ "$HTTP_CODE" = "404" ]; then
                warn "  ⚠ HTTPS可访问但返回404 (可能服务未就绪)"
            elif [ "$HTTP_CODE" = "503" ]; then
                warn "  ⚠ HTTPS返回503 (服务不可用)"
            elif [ "$HTTP_CODE" = "000" ]; then
                warn "  ⚠ 无法连接到 $host (请检查DNS配置或网络)"
            else
                warn "  ⚠ HTTPS返回 $HTTP_CODE"
            fi
            
            # 检查证书有效性
            CERT_CHECK=$(echo | openssl s_client -connect "$host:443" -servername "$host" 2>/dev/null | openssl x509 -noout -subject -dates 2>/dev/null || echo "")
            if [ -n "$CERT_CHECK" ]; then
                log "  ✓ 证书验证通过"
            else
                warn "  ⚠ 无法验证证书（可能需要配置DNS）"
            fi
        done
    else
        warn "curl 未安装，无法测试HTTPS访问"
    fi
else
    info "未找到配置的域名，跳过HTTPS测试"
fi

echo ""
echo "=========================================="
echo "验证完成"
echo "=========================================="
echo ""
info "如果发现问题，请参考: HTTPS_CERTIFICATE_CONFIG.md"

