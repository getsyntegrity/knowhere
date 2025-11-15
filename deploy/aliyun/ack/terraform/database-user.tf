# RDS 数据库和用户配置（需要在实例创建后单独配置）

# 创建数据库
resource "alicloud_db_database" "main" {
  instance_id = alicloud_db_instance.postgres.id
  name        = "knowhere"
  character_set = "UTF8"
  description = "Main database for knowhere application"
}

# 创建数据库用户
resource "alicloud_rds_account" "postgres" {
  db_instance_id   = alicloud_db_instance.postgres.id
  account_name     = "postgres"
  account_password = var.db_password
  account_type     = "Super"
  description      = "PostgreSQL superuser for knowhere"
}

