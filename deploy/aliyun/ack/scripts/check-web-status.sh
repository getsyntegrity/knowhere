#!/bin/bash

# Web服务诊断脚本 - 检查ACK集群中web服务的状态

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

# 从deploy-config.sh读取NAMESPACE（如果存在）
if [ -f "$(dirname "$0")/../../../deploy-config.sh" ]; then
    source "$(dirname "$0")/../../../deploy-config.sh" 2>/dev/null || true
fi

NAMESPACE=${NAMESPACE:-knowhere}

echo "=========================================="
echo "Web服务诊断检查"
echo "=========================================="
echo ""

# 1. 检查命名空间
echo "1. 检查命名空间..."
if kubectl get namespace "$NAMESPACE" &>/dev/null; then
    log "命名空间 '$NAMESPACE' 存在"
else
    error "命名空间 '$NAMESPACE' 不存在"
    exit 1
fi

# 2. 检查Deployment状态
echo ""
echo "2. 检查Web Deployment状态..."
if kubectl get deployment knowhere-web -n "$NAMESPACE" &>/dev/null; then
    log "Deployment 'knowhere-web' 存在"
    echo ""
    kubectl get deployment knowhere-web -n "$NAMESPACE" -o wide
    echo ""
    
    # 检查副本数
    DESIRED=$(kubectl get deployment knowhere-web -n "$NAMESPACE" -o jsonpath='{.spec.replicas}')
    READY=$(kubectl get deployment knowhere-web -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}')
    AVAILABLE=$(kubectl get deployment knowhere-web -n "$NAMESPACE" -o jsonpath='{.status.availableReplicas}')
    
    if [ "$READY" = "$DESIRED" ] && [ "$AVAILABLE" = "$DESIRED" ]; then
        log "副本状态正常: $READY/$DESIRED 就绪"
    else
        warn "副本状态异常: 就绪=$READY, 可用=$AVAILABLE, 期望=$DESIRED"
    fi
else
    error "Deployment 'knowhere-web' 不存在"
fi

# 3. 检查Pod状态
echo ""
echo "3. 检查Web Pod状态..."
WEB_PODS=$(kubectl get pods -n "$NAMESPACE" -l app=knowhere-web --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$WEB_PODS" -gt 0 ]; then
    log "找到 $WEB_PODS 个Web Pod"
    echo ""
    kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o wide
    echo ""
    
    # 检查每个Pod的详细状态
    kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.phase}{"\t"}{.status.containerStatuses[0].ready}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}' | while read -r line; do
        POD_NAME=$(echo "$line" | awk '{print $1}')
        PHASE=$(echo "$line" | awk '{print $2}')
        READY=$(echo "$line" | awk '{print $3}')
        RESTARTS=$(echo "$line" | awk '{print $4}')
        
        echo "  Pod: $POD_NAME"
        echo "    状态: $PHASE"
        echo "    就绪: $READY"
        echo "    重启次数: $RESTARTS"
        
        if [ "$PHASE" != "Running" ] || [ "$READY" != "true" ]; then
            warn "    Pod状态异常，查看详细信息："
            echo "    kubectl describe pod $POD_NAME -n $NAMESPACE"
        fi
        
        if [ "$RESTARTS" -gt 0 ]; then
            warn "    Pod已重启 $RESTARTS 次，查看日志："
            echo "    kubectl logs $POD_NAME -n $NAMESPACE --tail=50"
        fi
        echo ""
    done
else
    error "未找到Web Pod"
fi

# 4. 检查Pod事件和错误
echo ""
echo "4. 检查Pod事件..."
kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | while read -r pod_name; do
    if [ -n "$pod_name" ]; then
        echo "  Pod: $pod_name"
        EVENTS=$(kubectl get events -n "$NAMESPACE" --field-selector involvedObject.name="$pod_name" --sort-by='.lastTimestamp' --no-headers 2>/dev/null | tail -5)
        if [ -n "$EVENTS" ]; then
            echo "$EVENTS" | while read -r event; do
                TYPE=$(echo "$event" | awk '{print $2}')
                if [ "$TYPE" = "Warning" ]; then
                    error "    $event"
                else
                    info "    $event"
                fi
            done
        else
            info "    无最近事件"
        fi
        echo ""
    fi
done

# 5. 检查环境变量配置
echo ""
echo "5. 检查环境变量配置..."
FIRST_POD=$(kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$FIRST_POD" ]; then
    log "检查Pod '$FIRST_POD' 的环境变量："
    echo ""
    
    # 检查NEXT_PUBLIC_*环境变量
    ENV_VARS=$(kubectl get pod "$FIRST_POD" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].env[*].name}' 2>/dev/null)
    echo "  已配置的环境变量："
    kubectl get pod "$FIRST_POD" -n "$NAMESPACE" -o jsonpath='{range .spec.containers[0].env[*]}{.name}{"="}{.value}{"\n"}{end}' | while read -r env_line; do
        if echo "$env_line" | grep -q "NEXT_PUBLIC"; then
            VAR_NAME=$(echo "$env_line" | cut -d'=' -f1)
            VAR_VALUE=$(echo "$env_line" | cut -d'=' -f2-)
            if [ -n "$VAR_VALUE" ]; then
                # 检查是否包含中文字符
                if echo "$VAR_VALUE" | grep -qP '[\x{4e00}-\x{9fff}]'; then
                    log "    $VAR_NAME = $VAR_VALUE (包含中文)"
                else
                    log "    $VAR_NAME = $VAR_VALUE"
                fi
            else
                warn "    $VAR_NAME = (空值)"
            fi
        fi
    done
    echo ""
    
    # 检查Deployment中的环境变量定义
    echo "  Deployment中定义的环境变量："
    kubectl get deployment knowhere-web -n "$NAMESPACE" -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}{"="}{.value}{"\n"}{end}' | while read -r env_line; do
        if echo "$env_line" | grep -q "NEXT_PUBLIC"; then
            VAR_NAME=$(echo "$env_line" | cut -d'=' -f1)
            VAR_VALUE=$(echo "$env_line" | cut -d'=' -f2-)
            if [ -n "$VAR_VALUE" ]; then
                if echo "$VAR_VALUE" | grep -qP '[\x{4e00}-\x{9fff}]'; then
                    info "    $VAR_NAME = $VAR_VALUE (包含中文)"
                else
                    info "    $VAR_NAME = $VAR_VALUE"
                fi
            else
                warn "    $VAR_NAME = (空值或未设置)"
            fi
        fi
    done
else
    warn "无法获取Pod信息，跳过环境变量检查"
fi

# 6. 检查Service状态
echo ""
echo "6. 检查Service状态..."
if kubectl get service knowhere-web -n "$NAMESPACE" &>/dev/null; then
    log "Service 'knowhere-web' 存在"
    echo ""
    kubectl get service knowhere-web -n "$NAMESPACE" -o wide
    echo ""
    
    # 检查Endpoints
    ENDPOINTS=$(kubectl get endpoints knowhere-web -n "$NAMESPACE" -o jsonpath='{.subsets[*].addresses[*].ip}' 2>/dev/null)
    if [ -n "$ENDPOINTS" ]; then
        log "Service有可用的Endpoints: $ENDPOINTS"
    else
        error "Service没有可用的Endpoints，Pod可能未就绪"
    fi
else
    error "Service 'knowhere-web' 不存在"
fi

# 7. 检查Ingress状态
echo ""
echo "7. 检查Ingress状态..."
if kubectl get ingress knowhere-ingress -n "$NAMESPACE" &>/dev/null; then
    log "Ingress 'knowhere-ingress' 存在"
    echo ""
    kubectl get ingress knowhere-ingress -n "$NAMESPACE" -o wide
    echo ""
    
    # 检查Ingress地址
    INGRESS_ADDR=$(kubectl get ingress knowhere-ingress -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)
    if [ -z "$INGRESS_ADDR" ]; then
        INGRESS_ADDR=$(kubectl get ingress knowhere-ingress -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
    fi
    
    if [ -n "$INGRESS_ADDR" ]; then
        log "Ingress地址: $INGRESS_ADDR"
    else
        warn "Ingress地址未分配，可能正在创建中"
    fi
    
    # 检查Ingress规则
    echo ""
    echo "  Ingress规则："
    kubectl describe ingress knowhere-ingress -n "$NAMESPACE" | grep -A 10 "Rules:" || true
else
    warn "Ingress 'knowhere-ingress' 不存在"
fi

# 8. 检查Pod日志（最近50行）
echo ""
echo "8. 检查Pod日志（最近50行）..."
kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | while read -r pod_name; do
    if [ -n "$pod_name" ]; then
        echo "  Pod: $pod_name"
        echo "  ---"
        kubectl logs "$pod_name" -n "$NAMESPACE" --tail=50 2>&1 | head -20 | sed 's/^/    /'
        echo ""
        
        # 检查是否有错误
        ERROR_COUNT=$(kubectl logs "$pod_name" -n "$NAMESPACE" 2>&1 | grep -i "error\|fatal\|exception" | wc -l | tr -d ' ')
        if [ "$ERROR_COUNT" -gt 0 ]; then
            warn "    发现 $ERROR_COUNT 条错误日志"
            echo "    查看完整日志: kubectl logs $pod_name -n $NAMESPACE"
        fi
        echo ""
    fi
done

# 9. 检查节点分布
echo ""
echo "9. 检查Pod节点分布..."
kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}' | while read -r line; do
    POD_NAME=$(echo "$line" | awk '{print $1}')
    NODE_NAME=$(echo "$line" | awk '{print $2}')
    if [ -n "$POD_NAME" ] && [ -n "$NODE_NAME" ]; then
        info "  $POD_NAME -> $NODE_NAME"
    fi
done

# 10. 检查YAML配置中的环境变量（检查是否有编码问题）
echo ""
echo "10. 检查Deployment YAML配置..."
DEPLOYMENT_YAML=$(kubectl get deployment knowhere-web -n "$NAMESPACE" -o yaml 2>/dev/null)
if echo "$DEPLOYMENT_YAML" | grep -q "SIMPLE_COMPANY_NAME"; then
    SIMPLE_NAME_VALUE=$(echo "$DEPLOYMENT_YAML" | grep -A 1 "SIMPLE_COMPANY_NAME" | grep "value:" | sed 's/.*value: *//' | tr -d '"' | tr -d "'")
    if [ -n "$SIMPLE_NAME_VALUE" ]; then
        log "找到 SIMPLE_COMPANY_NAME = $SIMPLE_NAME_VALUE"
        
        # 检查值是否正确
        if echo "$SIMPLE_NAME_VALUE" | grep -qP '[\x{4e00}-\x{9fff}]'; then
            log "  值包含中文字符，检查编码..."
            # 尝试检查是否有编码问题
            if echo "$SIMPLE_NAME_VALUE" | grep -q "渊维科技"; then
                log "  值正确: 包含'渊维科技'"
            else
                warn "  值可能不正确或存在编码问题"
            fi
        fi
    else
        warn "SIMPLE_COMPANY_NAME 值为空"
    fi
else
    warn "未找到 SIMPLE_COMPANY_NAME 环境变量"
fi

# 11. 测试Pod内部连接
echo ""
echo "11. 测试Pod内部连接..."
FIRST_POD=$(kubectl get pods -n "$NAMESPACE" -l app=knowhere-web -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$FIRST_POD" ]; then
    log "测试Pod '$FIRST_POD' 的HTTP连接..."
    HTTP_STATUS=$(kubectl exec "$FIRST_POD" -n "$NAMESPACE" -- wget -q -O- -T 5 http://localhost:3000 2>&1 | head -1 || echo "FAILED")
    if echo "$HTTP_STATUS" | grep -q "FAILED\|timeout\|Connection refused"; then
        error "  Pod内部HTTP连接失败"
    else
        log "  Pod内部HTTP连接正常"
    fi
else
    warn "无法获取Pod进行连接测试"
fi

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
echo ""
echo "如果发现问题，可以运行以下命令获取更多信息："
echo "  # 查看Pod详细信息"
echo "  kubectl describe pod <pod-name> -n $NAMESPACE"
echo ""
echo "  # 查看完整日志"
echo "  kubectl logs <pod-name> -n $NAMESPACE"
echo ""
echo "  # 查看Deployment配置"
echo "  kubectl get deployment knowhere-web -n $NAMESPACE -o yaml"
echo ""
echo "  # 查看Service配置"
echo "  kubectl get service knowhere-web -n $NAMESPACE -o yaml"
echo ""

