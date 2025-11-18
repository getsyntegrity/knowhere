# NAS文件存储 - 用于模型缓存共享存储
# 注意：如果 NAS 服务未开通，请暂时注释以下资源，等开通后再启用

# resource "alicloud_nas_file_system" "model_cache" {
#   protocol_type    = "NFS"
#   storage_type     = "Performance"
#   description      = "${var.project_name}-${var.environment}-model-cache"
#   file_system_type = "standard"
#
#   tags = {
#     Name        = "${var.project_name}-${var.environment}-model-cache"
#     Environment = var.environment
#     Project     = var.project_name
#   }
# }

# NAS挂载点
# resource "alicloud_nas_mount_target" "model_cache" {
#   count = length(alicloud_vswitch.private)
#
#   file_system_id    = alicloud_nas_file_system.model_cache.id
#   access_group_name = alicloud_nas_access_group.model_cache.access_group_name
#   vswitch_id        = alicloud_vswitch.private[count.index].id
# }

# NAS访问组
# resource "alicloud_nas_access_group" "model_cache" {
#   access_group_name = "knowheredevmodelcache"
#   access_group_type = "Vpc"
#   description       = "Access group for model cache"
# }

# NAS访问规则 - 允许VPC内访问
# resource "alicloud_nas_access_rule" "model_cache" {
#   access_group_name = alicloud_nas_access_group.model_cache.access_group_name
#   source_cidr_ip    = alicloud_vpc.main.cidr_block
#   rw_access_type    = "RDWR"
#   user_access_type  = "no_squash"
#   priority          = 1
# }

# 输出（暂时注释，等 NAS 资源启用后再取消注释）
# output "nas_file_system_id" {
#   description = "NAS文件系统ID"
#   value       = alicloud_nas_file_system.model_cache.id
# }
#
# output "nas_mount_target_domain" {
#   description = "NAS挂载目标域名"
#   value       = alicloud_nas_mount_target.model_cache[0].mount_target_domain
# }
