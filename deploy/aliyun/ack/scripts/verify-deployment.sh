#!/bin/bash

# 部署验证脚本 - 验证ACK集群优化部署

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

echo "=========================================="
echo "ACK集群优化部署验证"
echo "=========================================="
echo ""

# 1. 检查Service类型
echo "1. 检查Service配置..."
SVC_TYPES=$(kubectl get svc -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.spec.type}{"\n"}{end}')
if echo "$SVC_TYPES" | grep -q "LoadBalancer"; then
    error "发现LoadBalancer类型的Service，应该使用ClusterIP"
    echo "$SVC_TYPES" | grep "LoadBalancer"
else
    log "所有Service都是ClusterIP类型"
fi

# 2. 检查HPA
echo ""
echo "2. 检查HPA配置..."
HPA_COUNT=$(kubectl get hpa -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$HPA_COUNT" -ge 3 ]; then
    log "HPA已配置 ($HPA_COUNT个)"
    kubectl get hpa -n "$NAMESPACE" --no-headers | while read -r line; do
        name=$(echo "$line" | awk '{print $1}')
        replicas=$(echo "$line" | awk '{print $6}')
        min=$(echo "$line" | awk '{print $4}')
        max=$(echo "$line" | awk '{print $5}')
        info "  $name: $replicas (范围: $min-$max)"
    done
else
    warn "HPA配置不完整 (期望3个，实际$HPA_COUNT个)"
fi

# 3. 检查PDB
echo ""
echo "3. 检查PodDisruptionBudget..."
PDB_COUNT=$(kubectl get pdb -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$PDB_COUNT" -ge 3 ]; then
    log "PDB已配置 ($PDB_COUNT个)"
else
    warn "PDB配置不完整 (期望3个，实际$PDB_COUNT个)"
fi

# 4. 检查Pod分布
echo ""
echo "4. 检查Pod分布..."
POD_NODES=$(kubectl get pods -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}')
UNIQUE_NODES=$(echo "$POD_NODES" | awk '{print $2}' | sort -u | wc -l | tr -d ' ')
if [ "$UNIQUE_NODES" -ge 2 ]; then
    log "Pod分布在 $UNIQUE_NODES 个节点上"
    echo "$POD_NODES" | awk '{print "  " $1 ": " $2}'
else
    warn "Pod可能未跨节点分布 (当前分布在 $UNIQUE_NODES 个节点)"
fi

# 5. 检查资源限制
echo ""
echo "5. 检查资源限制..."
kubectl get deployment -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].resources.limits.cpu}{"\t"}{.spec.template.spec.containers[0].resources.limits.memory}{"\n"}{end}' | while read -r line; do
    name=$(echo "$line" | awk '{print $1}')
    cpu=$(echo "$line" | awk '{print $2}')
    mem=$(echo "$line" | awk '{print $3}')
    info "  $name: CPU=$cpu, Memory=$mem"
done

# 6. 检查Ingress
echo ""
echo "6. 检查Ingress配置..."
INGRESS_COUNT=$(kubectl get ingress -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$INGRESS_COUNT" -ge 1 ]; then
    log "Ingress已配置"
    kubectl get ingress -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.spec.rules[*].host}{"\n"}{end}' | while read -r line; do
        info "  $line"
    done
else
    warn "Ingress未配置"
fi

# 7. 检查Ingress Controller
echo ""
echo "7. 检查Ingress Controller..."
if kubectl get pods -A | grep -qi ingress; then
    log "Ingress Controller已安装"
    kubectl get pods -A | grep -i ingress | head -3
else
    warn "Ingress Controller未安装"
    info "  安装命令: ./install-ingress-controller.sh"
fi

# 8. 检查节点数
echo ""
echo "8. 检查节点数..."
NODE_COUNT=$(kubectl get nodes --no-headers | wc -l | tr -d ' ')
info "当前节点数: $NODE_COUNT"
if [ "$NODE_COUNT" -ge 2 ]; then
    log "节点数符合要求 (最小2个)"
else
    warn "节点数不足 (当前$NODE_COUNT个，最小需要2个)"
fi

# 9. 检查metrics-server
echo ""
echo "9. 检查metrics-server..."
if kubectl get deployment metrics-server -n kube-system &>/dev/null; then
    log "metrics-server已安装"
else
    warn "metrics-server未安装，HPA可能无法工作"
fi

# 10. 检查Pod状态
echo ""
echo "10. 检查Pod状态..."
RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
TOTAL_PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$RUNNING_PODS" -eq "$TOTAL_PODS" ]; then
    log "所有Pod运行正常 ($RUNNING_PODS/$TOTAL_PODS)"
else
    warn "部分Pod未运行 ($RUNNING_PODS/$TOTAL_PODS)"
    kubectl get pods -n "$NAMESPACE" | grep -v Running
fi

# 11. 检查自动扩容能力
echo ""
echo "11. 检查自动扩容配置..."
echo "HPA状态:"
kubectl get hpa -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[?(@.type=="AbleToScale")].status}{"\n"}{end}' | while read -r line; do
    name=$(echo "$line" | awk '{print $1}')
    status=$(echo "$line" | awk '{print $2}')
    if [ "$status" = "True" ]; then
        log "  $name: 可以扩容"
    else
        warn "  $name: 无法扩容 ($status)"
    fi
done

# 12. 检查HTTPS/TLS配置
echo ""
echo "12. 检查HTTPS/TLS配置..."
if kubectl get secret knowhere-tls -n "$NAMESPACE" &>/dev/null; then
    log "TLS Secret 'knowhere-tls' 已存在"
    
    # 检查Ingress是否引用了TLS Secret
    INGRESS_TLS=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].spec.tls[*].secretName}' 2>/dev/null || echo "")
    if echo "$INGRESS_TLS" | grep -q "knowhere-tls"; then
        log "Ingress已配置TLS，引用Secret: knowhere-tls"
        
        # 检查证书有效期
        if command -v openssl &> /dev/null; then
            CERT_DATA=$(kubectl get secret knowhere-tls -n "$NAMESPACE" -o jsonpath='{.data.tls\.crt}' 2>/dev/null || echo "")
            if [ -n "$CERT_DATA" ]; then
                CERT_EXPIRY=$(echo "$CERT_DATA" | base64 -d 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")
                if [ -n "$CERT_EXPIRY" ]; then
                    info "  证书到期时间: $CERT_EXPIRY"
                fi
            fi
        fi
    else
        warn "Ingress未引用TLS Secret"
    fi
else
    warn "TLS Secret 'knowhere-tls' 不存在，HTTPS可能无法正常工作"
    info "  创建命令: ./create-tls-secret.sh"
fi

# 13. 检查HTTPS访问（如果可能）
echo ""
echo "13. 检查HTTPS访问..."
INGRESS_HOSTS=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[*].spec.rules[*].host}' 2>/dev/null || echo "")
if [ -n "$INGRESS_HOSTS" ]; then
    INGRESS_IP=$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [ -n "$INGRESS_IP" ]; then
        info "Ingress Controller IP: $INGRESS_IP"
        for host in $INGRESS_HOSTS; do
            info "  测试HTTPS访问: https://$host"
            if command -v curl &> /dev/null; then
                HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 -k "https://$host" 2>/dev/null || echo "000")
                if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
                    log "  ✓ $host: HTTPS可访问 (HTTP $HTTP_CODE)"
                elif [ "$HTTP_CODE" != "000" ]; then
                    warn "  ⚠ $host: HTTPS返回 $HTTP_CODE"
                else
                    info "  - $host: 无法连接（可能需要配置DNS）"
                fi
            fi
        done
    else
        info "Ingress Controller IP未分配或无法获取"
    fi
fi

echo ""
echo "=========================================="
echo "验证完成"
echo "=========================================="

