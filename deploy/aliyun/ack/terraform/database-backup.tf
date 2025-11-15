# RDS 备份配置（使用独立的资源）
resource "alicloud_db_backup_policy" "postgres" {
  instance_id     = alicloud_db_instance.postgres.id
  backup_time     = "03:00Z-04:00Z"
  backup_period   = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  retention_period = 30
}

