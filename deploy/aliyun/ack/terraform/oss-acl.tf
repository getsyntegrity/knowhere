# OSS Bucket ACL 配置（使用独立的资源）
resource "alicloud_oss_bucket_acl" "main" {
  bucket = alicloud_oss_bucket.main.bucket
  acl    = "private"
}

